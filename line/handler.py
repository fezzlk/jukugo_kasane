import json

from line.image_store import BaseImageStore
from line.parser import LineCommandParser
from line.profile import LineProfileClient
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
        profile_client: Optional[LineProfileClient] = None,
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
        self.profile_client = profile_client or LineProfileClient(
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
            welcome = self.texts.get("welcome_prefix", "") + self.texts.get("usage", "")
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
        if source_type in ("group", "room"):
            self._handle_group_message(
                event, message, user_key, font_key, text, reply_token
            )
            return

        bulk_updates = self._parse_bulk_quiz_list(text)
        if bulk_updates is not None:
            if not self._apply_bulk_quiz_update(user_key, bulk_updates):
                msg = self._text_message(self.texts.get("bulk_update_failed", ""))
                self._reply(reply_token, [msg])
                return
            msg = self._text_message(self.texts.get("bulk_update_success", ""))
            self._reply(reply_token, [msg])
            return

        command = self.parser.parse(text)
        if text.startswith("font_"):
            value = text[len("font_") :].strip()
            if value:
                command = {"type": "font", "value": value}
        if self._handle_menu_commands(command, user_key, source_type, reply_token):
            return
        if self._handle_user_quiz_registration(text, user_key, reply_token):
            return
        if command["type"] == "both":
            self._handle_user_quiz_images(command, font_key, reply_token)
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

        if command["type"] == "both":
            word = command.get("word", "")
            if not word:
                self._reply(
                    reply_token, [self._text_message(self.texts.get("need_word", ""))]
                )
                return
            if len(word) >= 2 and not self.parser._is_allowed_word(word):
                msg = self._text_message(self.texts.get("invalid_word", ""))
                self._reply(reply_token, [msg])
                return
            try:
                messages = []
                synth_result = self.texts.get("synth_result", "「{word}」の合成結果です。")
                messages.append(
                    self._text_message(synth_result.format(word=word))
                )
                if len(word) >= 3:
                    q_path, a_path, u_path = self.generator.generate_images_with_union(
                        word, font_key
                    )
                    q_url = self.image_store.get_image_url("q", word, font_key, q_path)
                    u_url = self.image_store.get_image_url("u", word, font_key, u_path)
                    messages.append(self._image_message(q_url))
                    messages.append(self._image_message(u_url))

                    video_path, preview_path = self.generator.generate_union_video(
                        word, font_key, fps=1
                    )
                    video_url = self.image_store.get_video_url(
                        "v", word, font_key, video_path
                    )
                    preview_url = self.image_store.get_image_url(
                        "p", word, font_key, preview_path
                    )
                    messages.append(
                        {
                            "type": "video",
                            "originalContentUrl": video_url,
                            "previewImageUrl": preview_url,
                        }
                    )
                    self._reply(reply_token, messages)
                    self.image_store.cleanup(
                        [q_path, a_path, u_path, video_path, preview_path]
                    )
                else:
                    q_path, a_path, u_path = self.generator.generate_images_with_union(
                        word, font_key
                    )
                    q_url = self.image_store.get_image_url("q", word, font_key, q_path)
                    u_url = self.image_store.get_image_url("u", word, font_key, u_path)
                    messages.append(self._image_message(q_url))
                    messages.append(self._image_message(u_url))
                    if a_path:
                        a_url = self.image_store.get_image_url(
                            "a", word, font_key, a_path
                        )
                        messages.append(self._image_message(a_url))
                    self._reply(reply_token, messages)
                    self.image_store.cleanup([q_path, a_path, u_path])
            except Exception as exc:
                self.logger.error("LINE image generate error: %s", exc)
                err = f"{self.texts.get('error_prefix', '')}{exc}"
                self._reply(reply_token, [self._text_message(err)])
            return

        msg = self._text_message(self.texts.get("not_two_chars", ""))
        self._reply(reply_token, [msg])

    def _handle_menu_commands(
        self, command: dict, user_key: str, source_type: str, reply_token: str
    ) -> bool:
        if command["type"] == "help":
            msg = self._text_message(self.texts.get("usage", ""), True)
            self._reply(reply_token, [msg])
            return True
        if command["type"] == "menu_generate":
            msg = self._text_message(self.texts.get("generate_prompt", ""))
            self._reply(reply_token, [msg])
            return True
        if command["type"] == "menu_register":
            msg = self._text_message(self.texts.get("register_help", ""))
            self._reply(reply_token, [msg])
            return True
        if command["type"] == "menu_list":
            if source_type == "user":
                msg = self._text_message(self._build_quiz_list_text(user_key))
                self._reply(reply_token, [msg])
            return True
        if command["type"] == "menu_settings":
            message = self._text_message(self.texts.get("settings_prompt", ""))
            if self.settings_quick_reply_builder:
                settings_quick = self.settings_quick_reply_builder()
                if settings_quick:
                    message["quickReply"] = settings_quick
            self._reply(reply_token, [message])
            return True
        if command["type"] == "menu_mode":
            message = self._text_message(self.texts.get("mode_prompt", ""))
            if self.mode_quick_reply_builder:
                mode_quick = self.mode_quick_reply_builder()
                if mode_quick:
                    message["quickReply"] = mode_quick
            self._reply(reply_token, [message])
            return True
        if command["type"] == "menu_font":
            message = self._text_message(self.texts.get("font_prompt", ""))
            if self.font_quick_reply_builder:
                font_quick = self.font_quick_reply_builder()
                if font_quick:
                    message["quickReply"] = font_quick
            self._reply(reply_token, [message])
            return True
        if command["type"] == "mode_common":
            user_settings = self._get_user_settings(user_key)
            user_settings["quiz_mode"] = "intersection"
            self._save_user_settings(user_key, user_settings)
            msg = self._text_message(self.texts.get("mode_set_common", ""))
            self._reply(reply_token, [msg])
            return True
        if command["type"] == "mode_union":
            user_settings = self._get_user_settings(user_key)
            user_settings["quiz_mode"] = "union"
            self._save_user_settings(user_key, user_settings)
            msg = self._text_message(self.texts.get("mode_set_union", ""))
            self._reply(reply_token, [msg])
            return True
        if command["type"] == "menu_usage":
            msg = self._text_message(self.texts.get("usage", ""))
            self._reply(reply_token, [msg])
            return True
        if command["type"] == "invalid_word":
            msg = self._text_message(self.texts.get("invalid_word", ""))
            self._reply(reply_token, [msg])
            return True
        if command["type"] == "list":
            if source_type == "user":
                msg = self._text_message(self._build_quiz_list_text(user_key))
                self._reply(reply_token, [msg])
            return True
        if command["type"] == "font":
            return self._handle_font_command(command, user_key, reply_token)
        return False

    def _handle_font_command(
        self, command: dict, user_key: str, reply_token: str
    ) -> bool:
        try:
            font_key = self._normalize_font_key(command["value"])
        except ValueError as exc:
            self._reply(reply_token, [self._text_message(str(exc))])
            return True
        user_settings = self._get_user_settings(user_key)
        user_settings["font"] = font_key
        if not self._save_user_settings(user_key, user_settings):
            self._reply(
                reply_token,
                [self._text_message(self.texts.get("save_failed", ""))],
            )
            return True
        msg = self._text_message(
            self.texts.get("font_set", "").format(font=font_key),
            include_quick_reply=True,
        )
        self._reply(reply_token, [msg])
        return True

    def _handle_user_quiz_registration(
        self, text: str, user_key: str, reply_token: str
    ) -> bool:
        quiz_status = self._parse_quiz_message(text)
        if not quiz_status:
            return False
        status, number, word = quiz_status
        if status == "invalid_number":
            msg = self._text_message(self.texts.get("invalid_number", ""))
            self._reply(reply_token, [msg])
            return True
        if status == "invalid_length":
            msg = self._text_message(self.texts.get("not_two_chars", ""))
            self._reply(reply_token, [msg])
            return True
        if status == "invalid_word":
            msg = self._text_message(self.texts.get("invalid_word", ""))
            self._reply(reply_token, [msg])
            return True
        if status == "ok":
            old_word = self.quiz_store.set_word(user_key, number, word)
            msg = self._text_message(self._build_set_reply_text(number, word, old_word))
            self._reply(reply_token, [msg])
            return True
        return False

    def _handle_user_quiz_images(
        self, command: dict, font_key: str, reply_token: str
    ) -> None:
        word = command.get("word", "")
        if not word:
            self._reply(
                reply_token, [self._text_message(self.texts.get("need_word", ""))]
            )
            return
        if len(word) >= 2 and not self.parser._is_allowed_word(word):
            msg = self._text_message(self.texts.get("invalid_word", ""))
            self._reply(reply_token, [msg])
            return
        try:
            messages = []
            messages.append(self._text_message(f"「{word}」の合成結果です。"))
            if len(word) >= 3:
                q_path, a_path, u_path = self.generator.generate_images_with_union(
                    word, font_key
                )
                q_url = self.image_store.get_image_url("q", word, font_key, q_path)
                u_url = self.image_store.get_image_url("u", word, font_key, u_path)
                messages.append(self._image_message(q_url))
                messages.append(self._image_message(u_url))

                video_path, preview_path = self.generator.generate_union_video(
                    word, font_key, fps=1
                )
                video_url = self.image_store.get_video_url(
                    "v", word, font_key, video_path
                )
                preview_url = self.image_store.get_image_url(
                    "p", word, font_key, preview_path
                )
                messages.append(
                    {
                        "type": "video",
                        "originalContentUrl": video_url,
                        "previewImageUrl": preview_url,
                    }
                )
                self._reply(reply_token, messages)
                self.image_store.cleanup(
                    [q_path, a_path, u_path, video_path, preview_path]
                )
            else:
                q_path, a_path, u_path = self.generator.generate_images_with_union(
                    word, font_key
                )
                q_url = self.image_store.get_image_url("q", word, font_key, q_path)
                u_url = self.image_store.get_image_url("u", word, font_key, u_path)
                messages.append(self._image_message(q_url))
                messages.append(self._image_message(u_url))
                if a_path:
                    a_url = self.image_store.get_image_url("a", word, font_key, a_path)
                    messages.append(self._image_message(a_url))
                self._reply(reply_token, messages)
                self.image_store.cleanup([q_path, a_path, u_path])
        except Exception as exc:
            self.logger.error("LINE image generate error: %s", exc)
            err = f"{self.texts.get('error_prefix', '')}{exc}"
            self._reply(reply_token, [self._text_message(err)])

    def _handle_group_message(
        self,
        event: dict,
        message: dict,
        user_key: str,
        font_key: str,
        text: str,
        reply_token: str,
    ) -> None:
        mentionees = message.get("mention", {}).get("mentionees", [])
        if not mentionees:
            return
        sender_id = event.get("source", {}).get("userId", "")
        sender_key = f"user:{sender_id}" if sender_id else user_key
        remaining_text = self._strip_mention_text(text, mentionees).strip()
        tokens = remaining_text.split()
        command_tokens = tokens
        if tokens and tokens[0].startswith("@"):
            command_tokens = tokens[1:]
        command_text = " ".join(command_tokens).strip()
        last_token = tokens[-1] if tokens else ""

        if self._is_bot_mentioned(message):
            if command_text.startswith("答え"):
                number = self._parse_answer_release_number(command_text)
                if not number:
                    answer_release_format = self.texts.get(
                        "answer_release_format",
                        f"解答発表は「@{self.texts.get('bot_name', '文字合成ボット')} "
                        "答え (問題番号)」と送ってください。",
                    )
                    msg = self._text_message(answer_release_format)
                    self._reply(reply_token, [msg])
                    return
                stored_word = self.quiz_store.get_word(sender_key, number)
                if not stored_word:
                    template = self.texts.get(
                        "unregistered_template", "{number}問目は未登録です。"
                    )
                    msg = self._text_message(template.format(number=number))
                    self._reply(reply_token, [msg])
                    return
                sender_settings = self._get_user_settings(sender_key)
                sender_font = sender_settings.get("font", font_key)
                try:
                    if len(stored_word) >= 3:
                        video_path, preview_path = self.generator.generate_union_video(
                            stored_word, sender_font, fps=1
                        )
                        video_url = self.image_store.get_video_url(
                            "v", stored_word, sender_font, video_path
                        )
                        preview_url = self.image_store.get_image_url(
                            "p", stored_word, sender_font, preview_path
                        )
                        self._reply(
                            reply_token,
                            [
                                {
                                    "type": "video",
                                    "originalContentUrl": video_url,
                                    "previewImageUrl": preview_url,
                                }
                            ],
                        )
                        self.image_store.cleanup([video_path, preview_path])
                    else:
                        q_path, a_path, u_path = self.generator.generate_images_with_union(
                            stored_word, sender_font
                        )
                        a_url = self.image_store.get_image_url(
                            "a", stored_word, sender_font, a_path
                        )
                        self._reply(reply_token, [self._image_message(a_url)])
                        self.image_store.cleanup([q_path, a_path, u_path])
                except Exception as exc:
                    self.logger.error("LINE answer release error: %s", exc)
                    generate_failed = self.texts.get(
                        "generate_failed", "画像の生成に失敗しました。"
                    )
                    err = f"{self.texts.get('error_prefix', '')}{generate_failed}"
                    self._reply(reply_token, [self._text_message(err)])
                return
            number_text = command_text if command_text else last_token
            number = int(number_text) if number_text.isdigit() else 0
            if number < 1 or number > 10:
                bot_name = self.texts.get("bot_name", "文字合成ボット")
                quiz_format = self.texts.get("quiz_format", f"@{bot_name} (問題番号)")
                msg = self._text_message(f"出題時は「{quiz_format}」と送ってください。")
                self._reply(reply_token, [msg])
                return
            stored_word = self.quiz_store.get_word(sender_key, number)
            if not stored_word:
                template = self.texts.get(
                    "unregistered_template", "{number}問目は未登録です。"
                )
                msg = self._text_message(template.format(number=number))
                self._reply(reply_token, [msg])
                return
            sender_settings = self._get_user_settings(sender_key)
            sender_font = sender_settings.get("font", font_key)
            quiz_mode = sender_settings.get("quiz_mode", "intersection")
            display_name = self.profile_client.get_display_name(
                event.get("source", {}), sender_id
            )
            display_name = display_name or self.texts.get(
                "mention_fallback", "ユーザー"
            )
            answer_template = self.texts.get(
                "quiz_answer_template",
                "【解答フォーマット】\n@{name} {number}.(解答)",
            )
            answer_text = answer_template.format(name=display_name, number=number)
            try:
                if quiz_mode == "union":
                    q_path, a_path, u_path = self.generator.generate_images_with_union(
                        stored_word, sender_font
                    )
                    u_url = self.image_store.get_image_url(
                        "u", stored_word, sender_font, u_path
                    )
                    prompt = self.texts.get("quiz_prompt_union", "何の和集合？")
                    self._reply(
                        reply_token,
                        [
                            self._text_message(prompt),
                            self._image_message(u_url),
                            self._text_message(answer_text),
                        ],
                    )
                    self.image_store.cleanup([q_path, a_path, u_path])
                else:
                    q_path, a_path = self.generator.generate_images(
                        stored_word, sender_font
                    )
                    q_url = self.image_store.get_image_url(
                        "q", stored_word, sender_font, q_path
                    )
                    prompt = self.texts.get("quiz_prompt_common", "何の共通部分？")
                    self._reply(
                        reply_token,
                        [
                            self._text_message(prompt),
                            self._image_message(q_url),
                            self._text_message(answer_text),
                        ],
                    )
                    self.image_store.cleanup([q_path, a_path])
            except Exception as exc:
                self.logger.error("LINE group quiz generate error: %s", exc)
                generate_failed = self.texts.get(
                    "generate_failed", "画像の生成に失敗しました。"
                )
                err = f"{self.texts.get('error_prefix', '')}{generate_failed}"
                self._reply(reply_token, [self._text_message(err)])
            return

        if len(mentionees) == 1:
            target_id = mentionees[0].get("userId", "")
            if target_id and target_id != self.bot_user_id:
                answer_text = (
                    remaining_text if remaining_text and not tokens else last_token
                )
                quiz_status = self._parse_quiz_message(answer_text)
                if not quiz_status or quiz_status[0] != "ok":
                    answer_format = self.texts.get(
                        "answer_format",
                        "解答は以下のフォーマットで送信してください。\n@出題者へのメンション (問題番号).(解答)",
                    )
                    msg = self._text_message(answer_format)
                    self._reply(reply_token, [msg])
                    return
                _, number, word = quiz_status
                stored_word = self.quiz_store.get_word(f"user:{target_id}", number)
                if not stored_word:
                    template = self.texts.get(
                        "unregistered_template", "{number}問目は未登録です。"
                    )
                    msg = self._text_message(template.format(number=number))
                    self._reply(reply_token, [msg])
                    return
                if stored_word and stored_word == word:
                    result = self.texts.get("answer_correct", "正解")
                else:
                    result = self.texts.get("answer_incorrect", "不正解")
                display_name = self.profile_client.get_display_name(
                    event.get("source", {}), sender_id
                )
                mention = self._build_mention_message(sender_id, result, display_name)
                self._reply(reply_token, [mention])

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

    def _parse_quiz_message(self, text: str) -> Optional[tuple]:
        payload = text.strip()
        if "." not in payload:
            return None
        number_text, word = payload.split(".", 1)
        number_text = number_text.strip()
        word = word.strip()
        if not number_text.isdigit():
            return ("invalid_number", None, None)
        number = int(number_text)
        if number < 1 or number > 10:
            return ("invalid_number", None, None)
        if len(word) < 2 or len(word) > 8:
            return ("invalid_length", number, word)
        if not self.parser._is_allowed_word(word):
            return ("invalid_word", number, word)
        return ("ok", number, word)

    def _build_set_reply_text(self, number: int, word: str, old_word: str) -> str:
        dispatch_template = self.texts.get(
            "quiz_dispatch_template",
            f"グループで「@{self.texts.get('bot_name', '文字合成ボット')} "
            "{number}」と送ると出題されます。",
        )
        dispatch_text = dispatch_template.format(number=number)
        mode_note = self.texts.get(
            "quiz_mode_note",
            "共通部分/和集合どちらで出題するかは「#設定」から変更できます。",
        )
        answer_release = self.texts.get(
            "answer_release_format",
            f"解答発表は「@{self.texts.get('bot_name', '文字合成ボット')} "
            "答え (問題番号)」と送ってください。",
        )
        if old_word:
            return (
                f"{number}問目に「{word}」をセットしました。"
                f"元の熟語「{old_word}」を削除しました。\n"
                f"{dispatch_text}\n{answer_release}\n{mode_note}"
            )
        return (
            f"{number}問目に「{word}」をセットしました。\n"
            f"{dispatch_text}\n{answer_release}\n{mode_note}"
        )

    def _build_quiz_list_text(self, user_key: str) -> str:
        items = self.quiz_store.list_words(user_key)
        unset_label = self.texts.get("quiz_unset", "未設定")
        title = self.texts.get("quiz_list_title", "【問題一覧】")
        lines = [title]
        for number in range(1, 11):
            word = items.get(number, unset_label)
            lines.append(f"{number}. {word}")
        dispatch_list = self.texts.get("quiz_list_footer") or self.texts.get(
            "quiz_dispatch_list",
            f"グループで「@{self.texts.get('bot_name', '文字合成ボット')} "
            "(問題番号)」と送ると出題されます。",
        )
        lines.append(dispatch_list)
        return "\n".join(lines)

    def _parse_bulk_quiz_list(self, text: str) -> Optional[dict]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return None
        title = self.texts.get("quiz_list_title", "【問題一覧】")
        if not lines[0].startswith(title):
            return None
        entries = {}
        for line in lines[1:]:
            footer = self.texts.get("quiz_list_footer")
            if footer and line == footer:
                continue
            if line.startswith("グループで「@"):
                continue
            if "." not in line:
                return {}
            number_text, word = line.split(".", 1)
            number_text = number_text.strip()
            word = word.strip()
            if not number_text.isdigit():
                return {}
            number = int(number_text)
            if number < 1 or number > 10:
                return {}
            if number in entries:
                return {}
            entries[number] = word
        if not entries:
            return {}
        return entries

    def _apply_bulk_quiz_update(self, user_key: str, entries: dict) -> bool:
        unset_label = self.texts.get("quiz_unset", "未設定")
        for number in range(1, 11):
            if number not in entries:
                return False
            word = entries[number]
            if word == unset_label:
                self.quiz_store.delete_word(user_key, number)
                continue
            if len(word) < 2 or len(word) > 8:
                return False
            if not self.parser._is_allowed_word(word):
                return False
            self.quiz_store.set_word(user_key, number, word)
        return True

    def _is_bot_mentioned(self, message: dict) -> bool:
        mentionees = message.get("mention", {}).get("mentionees", []) if message else []
        for mentionee in mentionees:
            if mentionee.get("userId") == self.bot_user_id:
                return True
        return False

    def _build_mention_message(
        self, user_id: str, result: str, display_name: str = ""
    ) -> dict:
        name = display_name or self.texts.get("mention_fallback", "ユーザー")
        template = self.texts.get("answer_template", "{name}さん、{result}です。")
        return {"type": "text", "text": template.format(name=name, result=result)}

    def _strip_mention_text(self, text: str, mentionees: list) -> str:
        """Remove mention tokens from the message text."""
        if not mentionees:
            return text
        trimmed = text
        for mentionee in sorted(
            (m for m in mentionees if isinstance(m, dict)),
            key=lambda m: m.get("index", 0),
            reverse=True,
        ):
            index = mentionee.get("index")
            length = mentionee.get("length")
            if isinstance(index, int) and isinstance(length, int) and length > 0:
                trimmed = trimmed[:index] + trimmed[index + length :]
        return trimmed

    def _parse_answer_release_number(self, text: str) -> int:
        payload = text.strip()
        if not payload.startswith("答え"):
            return 0
        number_text = payload[len("答え") :].strip()
        if not number_text.isdigit():
            return 0
        number = int(number_text)
        if number < 1 or number > 10:
            return 0
        return number
