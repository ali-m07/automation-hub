"""App settings (e.g. upload limits from app_settings table) and directory paths."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple

from . import db as _db

DEFAULT_MAX_UPLOAD_MB = 100
DEFAULT_MAX_FILES_PER_REQUEST = 20

# Directory paths
UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
GALLERY_DIR = Path("gallery")
TEMPLATES_PSD_DIR = Path("templates_psd")

# Ensure directories exist
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
GALLERY_DIR.mkdir(exist_ok=True)
TEMPLATES_PSD_DIR.mkdir(exist_ok=True)


def get_upload_limits() -> Tuple[int, int]:
    """Return (max_upload_bytes, max_files_per_request) from DB, then env, then defaults."""
    try:
        conn = _db.db_connect(_db.get_db_file())
        try:
            row_mb = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?", ("max_upload_mb",)
            ).fetchone()
            row_files = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?",
                ("max_files_per_request",),
            ).fetchone()
            mb = (
                int(_db.safe_row_get(row_mb, "value"))
                if row_mb and _db.safe_row_get(row_mb, "value")
                else int(os.getenv("MAX_UPLOAD_MB", str(DEFAULT_MAX_UPLOAD_MB)))
            )
            files = (
                int(_db.safe_row_get(row_files, "value"))
                if row_files and _db.safe_row_get(row_files, "value")
                else int(
                    os.getenv(
                        "MAX_FILES_PER_REQUEST", str(DEFAULT_MAX_FILES_PER_REQUEST)
                    )
                )
            )
        finally:
            conn.close()
        mb = max(1, min(mb, 10 * 1024))
        files = max(1, min(files, 1000))
        return (mb * 1024 * 1024, files)
    except Exception:
        mb = int(os.getenv("MAX_UPLOAD_MB", str(DEFAULT_MAX_UPLOAD_MB)))
        files = int(
            os.getenv("MAX_FILES_PER_REQUEST", str(DEFAULT_MAX_FILES_PER_REQUEST))
        )
        return (mb * 1024 * 1024, files)
