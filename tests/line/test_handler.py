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


def _build_handler(store, generator, logger, quick_reply_builder):
    class DummyImageStore:
        def __init__(self):
            self.calls = []
            self.cleaned = []

        def get_image_url(self, kind, word, font_key, local_path):
            self.calls.append((kind, word, font_key, local_path))
            return f"https://example.com/{kind}/{word}"

        def cleanup(self, paths):
            self.cleaned.append(list(paths))

    image_store = DummyImageStore()
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
            "settings_updated": "UPDATED {settings}",
            "font_set": "FONT {font}",
            "save_failed": "SAVE FAILED",
            "need_word": "NEED WORD",
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
        },
        quick_reply_builder=quick_reply_builder,
        default_font_key="default",
        image_store=image_store,
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
    assert generator.calls == [("ab", "default")]
    messages = captured["json"]["messages"]
    assert len(messages) == 3
    assert messages[0]["type"] == "text"
    assert messages[1]["originalContentUrl"].endswith("/q/ab")
    assert messages[2]["originalContentUrl"].endswith("/a/ab")


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
