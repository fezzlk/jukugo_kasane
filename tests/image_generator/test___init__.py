import os

import pytest

from image_generator import ImageGenerator


class DummyImage:
    def __init__(self):
        self.saved_paths = []

    def save(self, path):
        self.saved_paths.append(path)


def _no_op(*args, **kwargs):
    return None


def test_get_available_font_uses_first_existing_font(monkeypatch):
    sentinel_font = object()
    first_path = "/app/.fonts/Honoka_Shin_Mincho_L.otf"

    def fake_exists(path):
        return path == first_path

    def fake_truetype(path, size):
        assert path == first_path
        assert size == 1024
        return sentinel_font

    monkeypatch.setattr("image_generator.os.makedirs", _no_op)
    monkeypatch.setattr("image_generator.os.path.exists", fake_exists)
    monkeypatch.setattr("image_generator.ImageFont.truetype", fake_truetype)

    generator = ImageGenerator()

    assert generator.font is sentinel_font


def test_get_available_font_falls_back_to_default(monkeypatch):
    sentinel_font = object()

    monkeypatch.setattr("image_generator.os.makedirs", _no_op)
    monkeypatch.setattr("image_generator.os.path.exists", lambda _path: False)
    monkeypatch.setattr(
        "image_generator.ImageFont.load_default",
        lambda: sentinel_font,
    )

    generator = ImageGenerator()

    assert generator.font is sentinel_font


def test_generate_images_rejects_non_two_char_word(monkeypatch):
    monkeypatch.setattr("image_generator.os.makedirs", _no_op)
    monkeypatch.setattr(
        ImageGenerator, "_get_available_font", lambda _self: object()
    )

    generator = ImageGenerator()

    with pytest.raises(ValueError):
        generator.generate_images("abc")


def test_generate_images_saves_expected_paths(monkeypatch):
    dummy_q = DummyImage()
    dummy_a = DummyImage()

    monkeypatch.setattr("image_generator.os.makedirs", _no_op)
    monkeypatch.setattr(
        ImageGenerator, "_get_available_font", lambda _self: object()
    )
    monkeypatch.setattr(ImageGenerator, "_create_kanji_image", lambda *_: object())
    monkeypatch.setattr(
        ImageGenerator, "_process_pixels", lambda *_: (dummy_q, dummy_a)
    )

    generator = ImageGenerator()

    q_path, a_path = generator.generate_images("ab")

    assert q_path == os.path.join("images", "Q_ab.png")
    assert a_path == os.path.join("images", "A_ab.png")
    assert dummy_q.saved_paths == [q_path]
    assert dummy_a.saved_paths == [a_path]


def test_generate_images_rejects_invalid_font_key(monkeypatch):
    monkeypatch.setattr("image_generator.os.makedirs", _no_op)
    monkeypatch.setattr(
        ImageGenerator, "_get_available_font", lambda _self: object()
    )

    generator = ImageGenerator()

    with pytest.raises(ValueError):
        generator.generate_images("ab", "x")


def test_generate_images_uses_named_font_and_suffix(monkeypatch):
    sentinel_font = object()
    dummy_q = DummyImage()
    dummy_a = DummyImage()
    font_path = "/app/.fonts/Honoka_Shin_Mincho_L.otf"

    def fake_exists(path):
        return path == font_path

    def fake_truetype(path, size):
        assert path == font_path
        assert size == 1024
        return sentinel_font

    monkeypatch.setattr("image_generator.os.makedirs", _no_op)
    monkeypatch.setattr(
        ImageGenerator, "_get_available_font", lambda _self: object()
    )
    monkeypatch.setattr("image_generator.os.path.exists", fake_exists)
    monkeypatch.setattr("image_generator.ImageFont.truetype", fake_truetype)
    monkeypatch.setattr(ImageGenerator, "_create_kanji_image", lambda *_: object())
    monkeypatch.setattr(
        ImageGenerator, "_process_pixels", lambda *_: (dummy_q, dummy_a)
    )

    generator = ImageGenerator()

    q_path, a_path = generator.generate_images("ab", "mincho")

    assert q_path == os.path.join("images", "Q_ab_mincho.png")
    assert a_path == os.path.join("images", "A_ab_mincho.png")
    assert dummy_q.saved_paths == [q_path]
    assert dummy_a.saved_paths == [a_path]
