import json
import re

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
        quiz_store: Optional[object] = None,
        bot_user_id: str = "",
        settings_quick_reply_builder: Optional[Callable[[], Optional[dict]]] = None,
        mode_quick_reply_builder: Optional[Callable[[], Optional[dict]]] = None,
        font_quick_reply_builder: Optional[Callable[[], Optional[dict]]] = None,
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
        self.settings_quick_reply_builder = settings_quick_reply_builder
        self.mode_quick_reply_builder = mode_quick_reply_builder
        self.font_quick_reply_builder = font_quick_reply_builder
        self.default_font_key = default_font_key

        if image_store is None:
            raise ValueError("image_store is required.")
        self.image_store = image_store
        if quiz_store is None:
            raise ValueError("quiz_store is required.")
        self.quiz_store = quiz_store
        self.bot_user_id = bot_user_id
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
        source_type = event.get("source", {}).get("type")
        user_settings = self._get_user_settings(user_key)
        font_key = user_settings.get("font", self.default_font_key)

        text = message.get("text", "")
        command = self.parser.parse(text)
        if command["type"] == "help":
            msg = self._text_message(self.texts.get("usage", ""), True)
            self._reply(reply_token, [msg])
            return
        if command["type"] == "menu_generate":
            msg = self._text_message(self.texts.get("generate_prompt", ""))
            self._reply(reply_token, [msg])
            return
        if command["type"] == "menu_register":
            msg = self._text_message(self.texts.get("register_help", ""))
            self._reply(reply_token, [msg])
            return
        if command["type"] == "menu_list":
            if source_type == "user":
                msg = self._text_message(self._build_quiz_list_text(user_key))
                self._reply(reply_token, [msg])
            return
        if command["type"] == "menu_settings":
            message = self._text_message(self.texts.get("settings_prompt", ""))
            if self.settings_quick_reply_builder:
                settings_quick = self.settings_quick_reply_builder()
                if settings_quick:
                    message["quickReply"] = settings_quick
            self._reply(reply_token, [message])
            return
        if command["type"] == "menu_mode":
            message = self._text_message(self.texts.get("mode_prompt", ""))
            if self.mode_quick_reply_builder:
                mode_quick = self.mode_quick_reply_builder()
                if mode_quick:
                    message["quickReply"] = mode_quick
            self._reply(reply_token, [message])
            return
        if command["type"] == "menu_font":
            message = self._text_message(self.texts.get("font_prompt", ""))
            if self.font_quick_reply_builder:
                font_quick = self.font_quick_reply_builder()
                if font_quick:
                    message["quickReply"] = font_quick
            self._reply(reply_token, [message])
            return
        if command["type"] == "mode_common":
            user_settings["quiz_mode"] = "intersection"
            self._save_user_settings(user_key, user_settings)
            msg = self._text_message(self.texts.get("mode_set_common", ""))
            self._reply(reply_token, [msg])
            return
        if command["type"] == "mode_union":
            user_settings["quiz_mode"] = "union"
            self._save_user_settings(user_key, user_settings)
            msg = self._text_message(self.texts.get("mode_set_union", ""))
            self._reply(reply_token, [msg])
            return
        if command["type"] == "menu_usage":
            msg = self._text_message(self.texts.get("usage", ""))
            self._reply(reply_token, [msg])
            return
        if command["type"] == "invalid_word":
            msg = self._text_message(self.texts.get("invalid_word", ""))
            self._reply(reply_token, [msg])
            return
        if command["type"] == "list":
            if source_type == "user":
                msg = self._text_message(self._build_quiz_list_text(user_key))
                self._reply(reply_token, [msg])
            return

        if source_type == "user":
            set_payload = self._parse_quiz_set(text)
            if set_payload:
                number, word = set_payload
                if number == -1:
                    msg = self._text_message(self.texts.get("invalid_word", ""))
                    self._reply(reply_token, [msg])
                    return
                old_word = self.quiz_store.set_word(user_key, number, word)
                msg = self._text_message(
                    self._build_set_reply_text(number, word, old_word)
                )
                self._reply(reply_token, [msg])
                return

        if source_type in ("group", "room"):
            if self._is_group_quiz_enabled():
                if self._is_bot_mentioned(message):
                    number = self._extract_quiz_number(text)
                    if number:
                        sender_id = event.get("source", {}).get("userId", "")
                        sender_key = f"user:{sender_id}" if sender_id else user_key
                        sender_settings = self._get_user_settings(sender_key)
                        sender_font = sender_settings.get("font", font_key)
                        quiz_mode = sender_settings.get("quiz_mode", "intersection")
                        stored_word = self.quiz_store.get_word(sender_key, number)
                        if stored_word:
                            try:
                                if quiz_mode == "union":
                                    q_path, a_path, u_path = (
                                        self.generator.generate_images_with_union(
                                            stored_word, sender_font
                                        )
                                    )
                                    u_url = self.image_store.get_image_url(
                                        "u", stored_word, sender_font, u_path
                                    )
                                    self._reply(
                                        reply_token, [self._image_message(u_url)]
                                    )
                                    self.image_store.cleanup([q_path, a_path, u_path])
                                else:
                                    q_path, a_path = self.generator.generate_images(
                                        stored_word, sender_font
                                    )
                                    q_url = self.image_store.get_image_url(
                                        "q", stored_word, sender_font, q_path
                                    )
                                    self._reply(
                                        reply_token, [self._image_message(q_url)]
                                    )
                                    self.image_store.cleanup([q_path, a_path])
                            except Exception as exc:
                                self.logger.error(
                                    "LINE group quiz generate error: %s", exc
                                )
                        return
            answer_payload = self._parse_answer_submission(event)
            if answer_payload:
                if answer_payload[0] == "invalid":
                    sender_user_id = answer_payload[1]
                    mention = self._build_mention_message(
                        sender_user_id, self.texts.get("invalid_word", "")
                    )
                    self._reply(reply_token, [mention])
                    return
                target_user_id, sender_user_id, number, word = answer_payload
                stored_word = self.quiz_store.get_word(
                    f"user:{target_user_id}", number
                )
                if stored_word and stored_word == word:
                    result = self.texts.get("answer_correct", "正解")
                else:
                    result = self.texts.get("answer_incorrect", "不正解")
                mention = self._build_mention_message(sender_user_id, result)
                self._reply(reply_token, [mention])
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
            if len(word) == 2 and not self.parser._is_allowed_word(word):
                msg = self._text_message(self.texts.get("invalid_word", ""))
                self._reply(reply_token, [msg])
                return
            try:
                messages = []
                if command["type"] == "both":
                    q_path, a_path, u_path = self.generator.generate_images_with_union(
                        word, font_key
                    )
                    messages.append(
                        self._text_message(f"「{word}」の共通部分です。")
                    )
                    q_url = self.image_store.get_image_url(
                        "q", word, font_key, q_path
                    )
                    u_url = self.image_store.get_image_url(
                        "u", word, font_key, u_path
                    )
                    a_url = self.image_store.get_image_url(
                        "a", word, font_key, a_path
                    )
                    messages.append(self._image_message(q_url))
                    messages.append(self._image_message(u_url))
                    messages.append(self._image_message(a_url))
                    self._reply(reply_token, messages)
                    self.image_store.cleanup([q_path, a_path, u_path])
                else:
                    q_path, a_path = self.generator.generate_images(word, font_key)
                    if command["type"] == "question":
                        q_url = self.image_store.get_image_url(
                            "q", word, font_key, q_path
                        )
                        messages.append(self._image_message(q_url))
                    if command["type"] == "answer":
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

        msg = self._text_message(self.texts.get("not_two_chars", ""))
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

    def _parse_quiz_set(self, text: str) -> Optional[tuple]:
        match = self._match_quiz_pattern(text)
        if not match:
            return None
        number, word = match
        if not self.parser._is_allowed_word(word):
            return (-1, word)
        return number, word

    def _build_set_reply_text(self, number: int, word: str, old_word: str) -> str:
        if old_word:
            return f"第{number}問目に「{word}」をセットしました。元の熟語「{old_word}」を削除しました。"
        return f"第{number}問目に「{word}」をセットしました。"

    def _build_quiz_list_text(self, user_key: str) -> str:
        items = self.quiz_store.list_words(user_key)
        lines = ["問題集"]
        for number in range(1, 11):
            word = items.get(number, "未設定")
            lines.append(f"{number}. {word}")
        return "\n".join(lines)

    def _is_group_quiz_enabled(self) -> bool:
        return bool(self.bot_user_id)

    def _is_bot_mentioned(self, message: dict) -> bool:
        mentionees = (
            message.get("mention", {}).get("mentionees", [])
            if message
            else []
        )
        for mentionee in mentionees:
            if mentionee.get("userId") == self.bot_user_id:
                return True
        return False

    def _extract_quiz_number(self, text: str) -> int:
        match = re.search(r"\b(10|[1-9])\b", text)
        if match:
            return int(match.group(1))
        return 0

    def _parse_answer_submission(self, event: dict) -> Optional[tuple]:
        message = event.get("message", {})
        text = message.get("text", "")
        mentionees = message.get("mention", {}).get("mentionees", [])
        target = None
        sender_user_id = event.get("source", {}).get("userId", "")
        for mentionee in mentionees:
            user_id = mentionee.get("userId")
            if user_id and user_id != self.bot_user_id:
                target = user_id
                break
        if not target:
            return None
        match = self._match_quiz_pattern(text)
        if not match:
            return None
        number, word = match
        if not self.parser._is_allowed_word(word):
            return ("invalid", sender_user_id)
        return target, sender_user_id, number, word

    def _build_mention_message(self, user_id: str, result: str) -> dict:
        text = f"@user {result}"
        if not user_id:
            return {"type": "text", "text": result}
        return {
            "type": "text",
            "text": text,
            "mention": {
                "mentionees": [
                    {"index": 0, "length": 5, "userId": user_id},
                ]
            },
        }

    def _match_quiz_pattern(self, text: str) -> Optional[tuple]:
        match = re.search(r"(10|[1-9])\.(..)", text)
        if not match:
            return None
        number = int(match.group(1))
        word = match.group(2)
        return number, word
