import base64
import hashlib
import hmac
import json

from line.handler import LineHandler


class DummyGenerator:
    def __init__(self):
        self.calls = []

    def generate_images(self, word, font_key):
        self.calls.append((word, font_key))
        return (f"/tmp/Q_{word}.png", f"/tmp/A_{word}.png")

    def generate_images_with_union(self, word, font_key):
        self.calls.append((word, font_key, "union"))
        return (
            f"/tmp/Q_{word}.png",
            f"/tmp/A_{word}.png",
            f"/tmp/U_{word}.png",
        )

    def generate_union_video(self, word, font_key, fps=1):
        self.calls.append((word, font_key, "video", fps))
        return (f"/tmp/V_{word}.mp4", f"/tmp/P_{word}.png")

    def normalize_font_key(self, text):
        if text not in ("default", "mincho"):
            raise ValueError("invalid font")
        return text


class InMemoryStore:
    def __init__(self):
        self.data = {}

    def load_settings(self):
        return dict(self.data)

    def save_settings(self, settings):
        self.data = dict(settings)
        return True


class DummyLogger:
    def __init__(self):
        self.messages = []

    def error(self, msg, *args):
        if args:
            msg = msg % args
        self.messages.append(msg)


class DummyResponse:
    def __init__(self, status_code=200, text="OK"):
        self.status_code = status_code
        self.text = text


def _sign(body: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode("utf-8"), body, digestmod=hashlib.sha256).digest()
    return base64.b64encode(mac).decode("utf-8")


def _build_handler(
    store,
    generator,
    logger,
    quick_reply_builder,
    settings_builder=None,
    mode_builder=None,
    font_builder=None,
):
    class DummyImageStore:
        def __init__(self):
            self.calls = []
            self.cleaned = []

        def get_image_url(self, kind, word, font_key, local_path):
            self.calls.append((kind, word, font_key, local_path))
            return f"https://example.com/{kind}/{word}"

        def get_video_url(self, kind, word, font_key, local_path):
            self.calls.append((kind, word, font_key, local_path))
            return f"https://example.com/{kind}/{word}.mp4"

        def cleanup(self, paths):
            self.cleaned.append(list(paths))

    class DummyQuizStore:
        def __init__(self):
            self.data = {}

        def set_word(self, user_id, number, word):
            old_word = self.get_word(user_id, number)
            self.data.setdefault(user_id, {})[number] = word
            return old_word

        def get_word(self, user_id, number):
            return self.data.get(user_id, {}).get(number, "")

        def list_words(self, user_id):
            return dict(self.data.get(user_id, {}))

    image_store = DummyImageStore()
    quiz_store = DummyQuizStore()
    return LineHandler(
        channel_secret="secret",
        channel_access_token="token",
        server_fqdn="https://example.com",
        generator=generator,
        settings_store=store,
        logger=logger,
        texts={
            "welcome_prefix": "WELCOME ",
            "usage": "USAGE",
            "generate_prompt": "SEND TWO CHARS",
            "register_help": "REGISTER FORMAT",
            "settings_prompt": "SETTINGS PROMPT",
            "mode_prompt": "MODE PROMPT",
            "mode_set_common": "MODE COMMON",
            "mode_set_union": "MODE UNION",
            "font_prompt": "FONT PROMPT",
            "settings_updated": "UPDATED {settings}",
            "font_set": "FONT {font}",
            "save_failed": "SAVE FAILED",
            "need_word": "NEED WORD",
            "not_two_chars": "NOT TWO CHARS",
            "invalid_word": "INVALID WORD",
            "answer_correct": "CORRECT",
            "answer_incorrect": "INCORRECT",
            "error_prefix": "ERROR: ",
            "invalid_signature": "INVALID",
            "bad_request": "BAD",
        },
        keywords={
            "help": ["help"],
            "setting": "set",
            "font": "font",
            "question": "question",
            "answer": "answer",
            "list": "list",
            "menu_generate": "menu_generate",
            "menu_register": "menu_register",
            "menu_list": "menu_list",
            "menu_settings": "menu_settings",
            "menu_usage": "menu_usage",
            "menu_mode": "menu_mode",
            "menu_font": "menu_font",
            "mode_common": "mode_common",
            "mode_union": "mode_union",
        },
        quick_reply_builder=quick_reply_builder,
        default_font_key="default",
        image_store=image_store,
        quiz_store=quiz_store,
        settings_quick_reply_builder=settings_builder,
        mode_quick_reply_builder=mode_builder,
        font_quick_reply_builder=font_builder,
    )


def test_handle_callback_rejects_invalid_signature(monkeypatch):
    store = InMemoryStore()
    generator = DummyGenerator()
    logger = DummyLogger()
    handler = _build_handler(store, generator, logger, lambda: None)

    body = b'{"events":[]}'
    text, status = handler.handle_callback(body, "bad")
    assert status == 403
    assert text == "INVALID"


def test_follow_event_sends_welcome_message(monkeypatch):
    store = InMemoryStore()
    generator = DummyGenerator()
    logger = DummyLogger()
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr("line.reply.requests.post", fake_post)

    handler = _build_handler(store, generator, logger, lambda: {"items": []})
    payload = {"events": [{"type": "follow", "replyToken": "rt"}]}
    body = json.dumps(payload).encode("utf-8")
    signature = _sign(body, "secret")

    text, status = handler.handle_callback(body, signature)
    assert status == 200
    messages = captured["json"]["messages"]
    assert messages[0]["text"] == "WELCOME USAGE"
    assert "quickReply" in messages[0]


def test_text_message_returns_text_and_both_images(monkeypatch):
    store = InMemoryStore()
    generator = DummyGenerator()
    logger = DummyLogger()
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr("line.reply.requests.post", fake_post)

    handler = _build_handler(store, generator, logger, lambda: None)
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "rt",
                "message": {"type": "text", "text": "ab"},
                "source": {"userId": "u1"},
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign(body, "secret")

    text, status = handler.handle_callback(body, signature)
    assert status == 200
    assert generator.calls == [("ab", "default", "union")]
    messages = captured["json"]["messages"]
    assert len(messages) == 4
    assert messages[0]["type"] == "text"
    assert messages[1]["originalContentUrl"].endswith("/q/ab")
    assert messages[2]["originalContentUrl"].endswith("/u/ab")
    assert messages[3]["originalContentUrl"].endswith("/a/ab")


def test_text_message_returns_video_for_three_chars(monkeypatch):
    store = InMemoryStore()
    generator = DummyGenerator()
    logger = DummyLogger()
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr("line.reply.requests.post", fake_post)

    handler = _build_handler(store, generator, logger, lambda: None)
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "rt",
                "message": {"type": "text", "text": "abc"},
                "source": {"userId": "u1"},
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign(body, "secret")

    text, status = handler.handle_callback(body, signature)
    assert status == 200
    assert generator.calls == [
        ("abc", "default", "union"),
        ("abc", "default", "video", 1),
    ]
    messages = captured["json"]["messages"]
    assert messages[0]["type"] == "text"
    assert messages[1]["type"] == "image"
    assert messages[2]["type"] == "image"
    assert messages[3]["type"] == "video"


def test_font_command_updates_user_setting(monkeypatch):
    store = InMemoryStore()
    generator = DummyGenerator()
    logger = DummyLogger()
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr("line.reply.requests.post", fake_post)

    handler = _build_handler(store, generator, logger, lambda: None)
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "rt",
                "message": {"type": "text", "text": "font mincho"},
                "source": {"userId": "u1"},
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign(body, "secret")

    text, status = handler.handle_callback(body, signature)
    assert status == 200
    assert store.data == {"user:u1": {"font": "mincho"}}
    assert "FONT mincho" in captured["json"]["messages"][0]["text"]


def test_question_command_returns_question_image_only(monkeypatch):
    store = InMemoryStore()
    generator = DummyGenerator()
    logger = DummyLogger()
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr("line.reply.requests.post", fake_post)

    handler = _build_handler(store, generator, logger, lambda: None)
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "rt",
                "message": {"type": "text", "text": "question ab"},
                "source": {"userId": "u1"},
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign(body, "secret")

    text, status = handler.handle_callback(body, signature)
    assert status == 200
    messages = captured["json"]["messages"]
    assert len(messages) == 1
    assert messages[0]["originalContentUrl"].endswith("/q/ab")


def test_answer_command_returns_answer_image_only(monkeypatch):
    store = InMemoryStore()
    generator = DummyGenerator()
    logger = DummyLogger()
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr("line.reply.requests.post", fake_post)

    handler = _build_handler(store, generator, logger, lambda: None)
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "rt",
                "message": {"type": "text", "text": "answer ab"},
                "source": {"userId": "u1"},
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign(body, "secret")

    text, status = handler.handle_callback(body, signature)
    assert status == 200
    messages = captured["json"]["messages"]
    assert len(messages) == 1
    assert messages[0]["originalContentUrl"].endswith("/a/ab")


def test_setting_command_updates_font(monkeypatch):
    store = InMemoryStore()
    generator = DummyGenerator()
    logger = DummyLogger()
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr("line.reply.requests.post", fake_post)

    handler = _build_handler(store, generator, logger, lambda: None)
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "rt",
                "message": {"type": "text", "text": "set font=mincho"},
                "source": {"userId": "u1"},
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign(body, "secret")

    text, status = handler.handle_callback(body, signature)
    assert status == 200
    assert store.data == {"user:u1": {"font": "mincho"}}
    assert "UPDATED" in captured["json"]["messages"][0]["text"]


def test_help_command_returns_usage(monkeypatch):
    store = InMemoryStore()
    generator = DummyGenerator()
    logger = DummyLogger()
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr("line.reply.requests.post", fake_post)

    handler = _build_handler(store, generator, logger, lambda: None)
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "rt",
                "message": {"type": "text", "text": "help"},
                "source": {"userId": "u1"},
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign(body, "secret")

    text, status = handler.handle_callback(body, signature)
    assert status == 200
    assert captured["json"]["messages"][0]["text"] == "USAGE"


def test_menu_generate_returns_prompt(monkeypatch):
    store = InMemoryStore()
    generator = DummyGenerator()
    logger = DummyLogger()
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr("line.reply.requests.post", fake_post)

    handler = _build_handler(store, generator, logger, lambda: None)
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "rt",
                "message": {"type": "text", "text": "menu_generate"},
            "source": {"userId": "u1"},
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign(body, "secret")

    text, status = handler.handle_callback(body, signature)
    assert status == 200
    assert captured["json"]["messages"][0]["text"] == "SEND TWO CHARS"


def test_menu_register_returns_help(monkeypatch):
    store = InMemoryStore()
    generator = DummyGenerator()
    logger = DummyLogger()
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr("line.reply.requests.post", fake_post)

    handler = _build_handler(store, generator, logger, lambda: None)
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "rt",
                "message": {"type": "text", "text": "menu_register"},
                "source": {"type": "user", "userId": "u1"},
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign(body, "secret")

    text, status = handler.handle_callback(body, signature)
    assert status == 200
    assert captured["json"]["messages"][0]["text"] == "REGISTER FORMAT"


def test_menu_list_returns_quiz_list(monkeypatch):
    store = InMemoryStore()
    generator = DummyGenerator()
    logger = DummyLogger()
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr("line.reply.requests.post", fake_post)

    handler = _build_handler(store, generator, logger, lambda: None)
    handler.quiz_store.set_word("user:u1", 2, "ab")
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "rt",
                "message": {"type": "text", "text": "menu_list"},
                "source": {"type": "user", "userId": "u1"},
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign(body, "secret")

    text, status = handler.handle_callback(body, signature)
    assert status == 200
    message = captured["json"]["messages"][0]["text"]
    assert "1." in message
    assert "2. ab" in message


def test_menu_settings_returns_settings_quick_reply(monkeypatch):
    store = InMemoryStore()
    generator = DummyGenerator()
    logger = DummyLogger()
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr("line.reply.requests.post", fake_post)

    handler = _build_handler(
        store,
        generator,
        logger,
        lambda: None,
        settings_builder=lambda: {"items": [{"type": "action"}]},
    )
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "rt",
                "message": {"type": "text", "text": "menu_settings"},
                "source": {"type": "user", "userId": "u1"},
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign(body, "secret")

    text, status = handler.handle_callback(body, signature)
    assert status == 200
    message = captured["json"]["messages"][0]
    assert message["text"] == "SETTINGS PROMPT"
    assert "quickReply" in message


def test_menu_mode_returns_mode_quick_reply(monkeypatch):
    store = InMemoryStore()
    generator = DummyGenerator()
    logger = DummyLogger()
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr("line.reply.requests.post", fake_post)

    handler = _build_handler(
        store,
        generator,
        logger,
        lambda: None,
        mode_builder=lambda: {"items": [{"type": "action"}]},
    )
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "rt",
                "message": {"type": "text", "text": "menu_mode"},
                "source": {"type": "user", "userId": "u1"},
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign(body, "secret")

    text, status = handler.handle_callback(body, signature)
    assert status == 200
    message = captured["json"]["messages"][0]
    assert message["text"] == "MODE PROMPT"
    assert "quickReply" in message


def test_menu_font_returns_font_quick_reply(monkeypatch):
    store = InMemoryStore()
    generator = DummyGenerator()
    logger = DummyLogger()
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr("line.reply.requests.post", fake_post)

    handler = _build_handler(
        store,
        generator,
        logger,
        lambda: None,
        font_builder=lambda: {"items": [{"type": "action"}]},
    )
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "rt",
                "message": {"type": "text", "text": "menu_font"},
                "source": {"type": "user", "userId": "u1"},
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign(body, "secret")

    text, status = handler.handle_callback(body, signature)
    assert status == 200
    message = captured["json"]["messages"][0]
    assert message["text"] == "FONT PROMPT"
    assert "quickReply" in message


def test_mode_union_sets_setting(monkeypatch):
    store = InMemoryStore()
    generator = DummyGenerator()
    logger = DummyLogger()
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr("line.reply.requests.post", fake_post)

    handler = _build_handler(store, generator, logger, lambda: None)
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "rt",
                "message": {"type": "text", "text": "mode_union"},
                "source": {"type": "user", "userId": "u1"},
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign(body, "secret")

    text, status = handler.handle_callback(body, signature)
    assert status == 200
    assert store.data["user:u1"]["quiz_mode"] == "union"
    assert captured["json"]["messages"][0]["text"] == "MODE UNION"


def test_menu_usage_returns_usage(monkeypatch):
    store = InMemoryStore()
    generator = DummyGenerator()
    logger = DummyLogger()
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr("line.reply.requests.post", fake_post)

    handler = _build_handler(store, generator, logger, lambda: None)
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "rt",
                "message": {"type": "text", "text": "menu_usage"},
                "source": {"type": "user", "userId": "u1"},
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign(body, "secret")

    text, status = handler.handle_callback(body, signature)
    assert status == 200
    assert captured["json"]["messages"][0]["text"] == "USAGE"


def test_invalid_font_replies_with_error(monkeypatch):
    store = InMemoryStore()
    generator = DummyGenerator()
    logger = DummyLogger()
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr("line.reply.requests.post", fake_post)

    handler = _build_handler(store, generator, logger, lambda: None)
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "rt",
                "message": {"type": "text", "text": "font unknown"},
                "source": {"userId": "u1"},
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign(body, "secret")

    text, status = handler.handle_callback(body, signature)
    assert status == 200
    assert captured["json"]["messages"][0]["text"] == "invalid font"


def test_not_two_chars_returns_notice(monkeypatch):
    store = InMemoryStore()
    generator = DummyGenerator()
    logger = DummyLogger()
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr("line.reply.requests.post", fake_post)

    handler = _build_handler(store, generator, logger, lambda: None)
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "rt",
                "message": {"type": "text", "text": "a"},
                "source": {"userId": "u1"},
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign(body, "secret")

    text, status = handler.handle_callback(body, signature)
    assert status == 200
    assert captured["json"]["messages"][0]["text"] == "NOT TWO CHARS"


def test_invalid_word_replies_with_notice(monkeypatch):
    store = InMemoryStore()
    generator = DummyGenerator()
    logger = DummyLogger()
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr("line.reply.requests.post", fake_post)

    handler = _build_handler(store, generator, logger, lambda: None)
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "rt",
                "message": {"type": "text", "text": "a!"},
                "source": {"userId": "u1"},
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign(body, "secret")

    text, status = handler.handle_callback(body, signature)
    assert status == 200
    assert captured["json"]["messages"][0]["text"] == "INVALID WORD"


def test_quiz_register_with_three_chars(monkeypatch):
    store = InMemoryStore()
    generator = DummyGenerator()
    logger = DummyLogger()
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr("line.reply.requests.post", fake_post)

    handler = _build_handler(store, generator, logger, lambda: None)
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "rt",
                "message": {"type": "text", "text": "1.音楽性"},
                "source": {"type": "user", "userId": "u1"},
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign(body, "secret")

    text, status = handler.handle_callback(body, signature)
    assert status == 200
    assert handler.quiz_store.data["user:u1"][1] == "音楽性"


def test_quiz_register_invalid_word(monkeypatch):
    store = InMemoryStore()
    generator = DummyGenerator()
    logger = DummyLogger()
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr("line.reply.requests.post", fake_post)

    handler = _build_handler(store, generator, logger, lambda: None)
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "rt",
                "message": {"type": "text", "text": "1.ab!"},
                "source": {"type": "user", "userId": "u1"},
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign(body, "secret")

    text, status = handler.handle_callback(body, signature)
    assert status == 200
    assert captured["json"]["messages"][0]["text"] == "INVALID WORD"
