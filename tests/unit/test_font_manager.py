"""Tests for safe font discovery and uploads."""

from pathlib import Path

import pytest
from PIL import ImageFont

from automation_hub.services import font_manager


def _system_font_bytes() -> bytes:
    font = ImageFont.truetype("Arial.ttf", 16)
    path = Path(font.path)
    return path.read_bytes()


def test_store_list_resolve_and_deduplicate_font(monkeypatch, tmp_path):
    monkeypatch.setenv("FONT_DIR", str(tmp_path))
    content = _system_font_bytes()

    first, created = font_manager.store_font("My Font.ttf", content)
    duplicate, duplicate_created = font_manager.store_font("copy.ttf", content)

    assert created is True
    assert duplicate_created is False
    assert first["id"] == duplicate["id"]
    assert first["family"]
    assert font_manager.resolve_font(first["id"]).is_file()
    assert len(font_manager.list_fonts()) == 1


def test_store_font_rejects_invalid_extension(monkeypatch, tmp_path):
    monkeypatch.setenv("FONT_DIR", str(tmp_path))

    with pytest.raises(ValueError, match="Unsupported font type"):
        font_manager.store_font("font.exe", b"not-a-font")


def test_store_font_rejects_invalid_font_content(monkeypatch, tmp_path):
    monkeypatch.setenv("FONT_DIR", str(tmp_path))

    with pytest.raises(ValueError, match="not a readable font"):
        font_manager.store_font("broken.ttf", b"not-a-font")


def test_resolve_font_blocks_path_traversal(monkeypatch, tmp_path):
    monkeypatch.setenv("FONT_DIR", str(tmp_path / "fonts"))
    outside = tmp_path / "outside.ttf"
    outside.write_bytes(_system_font_bytes())

    assert font_manager.resolve_font("../outside.ttf") is None
