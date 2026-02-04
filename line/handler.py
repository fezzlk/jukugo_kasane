import json
from line.image_store import BaseImageStore
from line.parser import LineCommandParser
from line.reply import LineReplyClient
from line.signature import verify_signature
from typing import Callable, Dict, Optional


class LineHandler:
    """Handle LINE webhook events and reply with generated content."""

    def __init__(
        self,
        *,
        channel_secret: str,
        channel_access_token: str,
        server_fqdn: str,
        generator,
        settings_store,
        logger,
        texts: Dict[str, str],
        keywords: Dict[str, object],
        quick_reply_builder: Callable[[], Optional[dict]],
        default_font_key: str = "default",
        image_store: Optional[BaseImageStore] = None,
        parser: Optional[LineCommandParser] = None,
        reply_client: Optional[LineReplyClient] = None,
    ) -> None:
        """Initialize LINE handler dependencies and configuration."""
        self.channel_secret = channel_secret
        self.generator = generator
        self.settings_store = settings_store
        self.logger = logger
        self.texts = texts
        self.keywords = keywords
        self.quick_reply_builder = quick_reply_builder
        self.default_font_key = default_font_key

        if image_store is None:
            raise ValueError("image_store is required.")
        self.image_store = image_store
        self.parser = parser or LineCommandParser(keywords)
        self.reply_client = reply_client or LineReplyClient(
            channel_access_token, logger
        )

    def handle_callback(self, body: bytes, signature: str) -> tuple:
        """Validate signature and process webhook payload."""
        if not verify_signature(self.channel_secret, body, signature):
            return self.texts.get("invalid_signature", "Invalid signature"), 403

        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception as exc:
            self.logger.error("LINE webhook decode error: %s", exc)
            return self.texts.get("bad_request", "Bad Request"), 400

        events = payload.get("events", [])
        for event in events:
            self._handle_event(event)

        return "OK", 200

    def _reply(self, reply_token: str, messages: list) -> bool:
        """Send reply messages via LINE Messaging API."""
        return self.reply_client.reply(reply_token, messages)

    def _handle_event(self, event: dict) -> None:
        """Route a single event to the appropriate handler."""
        event_type = event.get("type")
        reply_token = event.get("replyToken")
        if not reply_token:
            return

        if event_type == "follow":
            welcome = self.texts.get("welcome_prefix", "") + self.texts.get(
                "usage", ""
            )
            message = self._text_message(welcome, include_quick_reply=True)
            self._reply(reply_token, [message])
            return

        if event_type != "message":
            return

        message = event.get("message", {})
        if message.get("type") != "text":
            return

        user_key = self._get_user_key(event)
        user_settings = self._get_user_settings(user_key)
        font_key = user_settings.get("font", self.default_font_key)

        command = self.parser.parse(message.get("text", ""))
        if command["type"] == "help":
            msg = self._text_message(self.texts.get("usage", ""), True)
            self._reply(reply_token, [msg])
            return

        if command["type"] == "setting":
            setting = command["setting"]
            if "font" in setting:
                try:
                    font_key = self._normalize_font_key(setting["font"])
                except ValueError as exc:
                    self._reply(reply_token, [self._text_message(str(exc))])
                    return
                user_settings["font"] = font_key
            if not self._save_user_settings(user_key, user_settings):
                self._reply(
                    reply_token,
                    [self._text_message(self.texts.get("save_failed", ""))],
                )
                return
            msg = self._text_message(
                self.texts.get("settings_updated", "").format(settings=user_settings),
                include_quick_reply=True,
            )
            self._reply(reply_token, [msg])
            return

        if command["type"] == "font":
            try:
                font_key = self._normalize_font_key(command["value"])
            except ValueError as exc:
                self._reply(reply_token, [self._text_message(str(exc))])
                return
            user_settings["font"] = font_key
            if not self._save_user_settings(user_key, user_settings):
                self._reply(
                    reply_token,
                    [self._text_message(self.texts.get("save_failed", ""))],
                )
                return
            msg = self._text_message(
                self.texts.get("font_set", "").format(font=font_key),
                include_quick_reply=True,
            )
            self._reply(reply_token, [msg])
            return

        if command["type"] in ("question", "answer", "both"):
            word = command.get("word", "")
            if not word:
                self._reply(
                    reply_token, [self._text_message(self.texts.get("need_word", ""))]
                )
                return
            try:
                q_path, a_path = self.generator.generate_images(word, font_key)
                messages = []
                if command["type"] == "both":
                    messages.append(
                        self._text_message(f"「{word}」の共通部分です。")
                    )
                if command["type"] in ("question", "both"):
                    q_url = self.image_store.get_image_url(
                        "q", word, font_key, q_path
                    )
                    messages.append(self._image_message(q_url))
                if command["type"] in ("answer", "both"):
                    a_url = self.image_store.get_image_url(
                        "a", word, font_key, a_path
                    )
                    messages.append(self._image_message(a_url))
                self._reply(reply_token, messages)
                self.image_store.cleanup([q_path, a_path])
            except Exception as exc:
                self.logger.error("LINE image generate error: %s", exc)
                err = f"{self.texts.get('error_prefix', '')}{exc}"
                self._reply(reply_token, [self._text_message(err)])
            return

        msg = self._text_message(self.texts.get("usage", ""), True)
        self._reply(reply_token, [msg])

    def _text_message(self, text: str, include_quick_reply: bool = False) -> dict:
        """Build a text message payload."""
        message = {"type": "text", "text": text}
        if include_quick_reply:
            quick_reply = self.quick_reply_builder()
            if quick_reply:
                message["quickReply"] = quick_reply
        return message

    def _image_message(self, url: str) -> dict:
        """Build an image message payload."""
        return {"type": "image", "originalContentUrl": url, "previewImageUrl": url}

    def _get_user_key(self, event: dict) -> str:
        """Return a stable key for the event source."""
        source = event.get("source", {})
        if source.get("userId"):
            return f"user:{source['userId']}"
        if source.get("groupId"):
            return f"group:{source['groupId']}"
        if source.get("roomId"):
            return f"room:{source['roomId']}"
        return "unknown"

    def _get_user_settings(self, user_key: str) -> dict:
        """Load stored settings for a user key."""
        settings = self.settings_store.load_settings()
        return settings.get(user_key, {})

    def _save_user_settings(self, user_key: str, user_settings: dict) -> bool:
        """Persist settings for a user key."""
        settings = self.settings_store.load_settings()
        settings[user_key] = user_settings
        return self.settings_store.save_settings(settings)

    def _normalize_font_key(self, text: str) -> str:
        """Normalize and validate a font key string."""
        return self.generator.normalize_font_key(text.strip().lower())
