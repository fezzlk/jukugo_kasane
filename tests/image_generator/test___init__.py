import types

import pytest

from image_generator import ImageGenerator


class DummyImage:
    def __init__(self):
        self.saved_paths = []

    def save(self, path):
        self.saved_paths.append(path)


def _build_generator(monkeypatch):
    monkeypatch.setattr(ImageGenerator, "_get_available_font", lambda self: object())
    monkeypatch.setattr("image_generator.os.makedirs", lambda *a, **k: None)
    return ImageGenerator(images_dir="images")


def test_normalize_font_key_accepts_default(monkeypatch):
    generator = _build_generator(monkeypatch)
    assert generator.normalize_font_key("") == "default"
    assert generator.normalize_font_key(None) == "default"


def test_normalize_font_key_rejects_invalid(monkeypatch):
    generator = _build_generator(monkeypatch)
    with pytest.raises(ValueError):
        generator.normalize_font_key("!")
    with pytest.raises(ValueError):
        generator.normalize_font_key("unknown")


def test_generate_images_raises_for_non_two_chars(monkeypatch):
    generator = _build_generator(monkeypatch)
    with pytest.raises(ValueError):
        generator.generate_images("a")


def test_generate_images_uses_suffix_and_saves(monkeypatch):
    generator = _build_generator(monkeypatch)
    dummy_q = DummyImage()
    dummy_a = DummyImage()

    monkeypatch.setattr(ImageGenerator, "_get_font_for_key", lambda self, key: object())
    monkeypatch.setattr(ImageGenerator, "_create_kanji_image", lambda *a, **k: object())
    monkeypatch.setattr(
        ImageGenerator, "_process_pixels", lambda *a, **k: (dummy_q, dummy_a)
    )

    q_path, a_path = generator.generate_images("ab", "mincho")
    assert q_path.endswith("Q_ab_mincho.png")
    assert a_path.endswith("A_ab_mincho.png")
    assert dummy_q.saved_paths == [q_path]
    assert dummy_a.saved_paths == [a_path]
