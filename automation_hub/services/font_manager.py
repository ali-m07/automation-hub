"""Font discovery, validation, and upload storage."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from PIL import ImageFont

SUPPORTED_FONT_EXTENSIONS = {".ttf", ".otf", ".ttc", ".woff", ".woff2"}
MAX_FONT_UPLOAD_BYTES = int(os.getenv("MAX_FONT_UPLOAD_MB", "20")) * 1024 * 1024


def get_font_dir() -> Path:
    path = Path(os.getenv("FONT_DIR", "fonts"))
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _font_id(path: Path) -> str:
    relative = path.resolve().relative_to(get_font_dir())
    return relative.as_posix()


def _font_metadata(path: Path) -> dict[str, Any]:
    font = ImageFont.truetype(str(path), 16)
    family, style = font.getname()
    return {
        "id": _font_id(path),
        "filename": path.name,
        "family": family or path.stem,
        "style": style or "Regular",
        "size": path.stat().st_size,
    }


def list_fonts() -> list[dict[str, Any]]:
    fonts = []
    for path in get_font_dir().rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_FONT_EXTENSIONS:
            continue
        try:
            fonts.append(_font_metadata(path))
        except (OSError, ValueError):
            continue
    return sorted(
        fonts,
        key=lambda item: (
            str(item["family"]).casefold(),
            str(item["style"]).casefold(),
            str(item["filename"]).casefold(),
        ),
    )


def resolve_font(font_id: str | None) -> Path | None:
    if not font_id:
        return None
    root = get_font_dir()
    candidate = (root / font_id).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if (
        not candidate.is_file()
        or candidate.suffix.lower() not in SUPPORTED_FONT_EXTENSIONS
    ):
        return None
    try:
        ImageFont.truetype(str(candidate), 16)
    except (OSError, ValueError):
        return None
    return candidate


def store_font(filename: str, content: bytes) -> tuple[dict[str, Any], bool]:
    if not content:
        raise ValueError("Font file is empty.")
    if len(content) > MAX_FONT_UPLOAD_BYTES:
        max_mb = MAX_FONT_UPLOAD_BYTES // (1024 * 1024)
        raise ValueError(f"Font file exceeds the {max_mb} MB limit.")

    suffix = Path(filename or "").suffix.lower()
    if suffix not in SUPPORTED_FONT_EXTENSIONS:
        allowed = ", ".join(sorted(SUPPORTED_FONT_EXTENSIONS))
        raise ValueError(f"Unsupported font type. Allowed: {allowed}")

    digest = hashlib.sha256(content).hexdigest()
    for item in list_fonts():
        existing = resolve_font(item["id"])
        if existing and hashlib.sha256(existing.read_bytes()).hexdigest() == digest:
            item["sha256"] = digest
            return item, False

    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(filename).stem).strip(".-_")
    safe_stem = safe_stem[:80] or "font"
    destination = get_font_dir() / f"{safe_stem}-{digest[:12]}{suffix}"

    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(dir=get_font_dir(), delete=False) as temp:
            temp.write(content)
            temp.flush()
            temp_name = temp.name
        ImageFont.truetype(temp_name, 16)
        os.replace(temp_name, destination)
        temp_name = None
    except (OSError, ValueError) as exc:
        raise ValueError("The uploaded file is not a readable font.") from exc
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)

    metadata = _font_metadata(destination)
    metadata["sha256"] = digest
    return metadata, True
