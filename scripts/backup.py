#!/usr/bin/env python3
"""
Automated backup script for Automation Hub.
Backs up SQLite DB and data directories (uploads, outputs, data_pools).
"""

import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

# Configuration
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "backups"))
DB_FILE = Path(os.getenv("APP_DATA_DIR", ".")) / "app.db"
UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
DATA_POOLS_DIR = Path(os.getenv("APP_DATA_DIR", ".")) / "data_pools"
GALLERY_DIR = Path("gallery")

BACKUP_DIR.mkdir(exist_ok=True)


def backup_database(db_path: Path, backup_zip: ZipFile) -> None:
    """Backup SQLite database."""
    if not db_path.exists():
        print(f"Warning: Database file not found: {db_path}")
        return
    backup_zip.write(db_path, "app.db")
    print(f"✓ Backed up database: {db_path}")


def backup_directory(
    dir_path: Path, backup_zip: ZipFile, arcname_prefix: str = ""
) -> None:
    """Backup a directory recursively."""
    if not dir_path.exists():
        print(f"Warning: Directory not found: {dir_path}")
        return
    count = 0
    for root, dirs, files in os.walk(dir_path):
        for file in files:
            file_path = Path(root) / file
            arcname = (
                f"{arcname_prefix}/{file_path.relative_to(dir_path.parent)}"
                if arcname_prefix
                else str(file_path.relative_to(dir_path.parent))
            )
            backup_zip.write(file_path, arcname)
            count += 1
    print(f"✓ Backed up {count} files from {dir_path}")


def main() -> None:
    """Create backup archive."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = BACKUP_DIR / f"automation_hub_backup_{timestamp}.zip"

    print(f"Creating backup: {backup_filename}")

    with ZipFile(backup_filename, "w") as zipf:
        # Backup database
        backup_database(DB_FILE, zipf)

        # Backup data directories
        backup_directory(UPLOAD_DIR, zipf, "uploads")
        backup_directory(OUTPUT_DIR, zipf, "outputs")
        backup_directory(DATA_POOLS_DIR, zipf, "data_pools")
        backup_directory(GALLERY_DIR, zipf, "gallery")

    size_mb = backup_filename.stat().st_size / (1024 * 1024)
    print(f"✓ Backup complete: {backup_filename} ({size_mb:.2f} MB)")

    # Cleanup old backups (keep last 30 days)
    cutoff_date = datetime.now().timestamp() - (30 * 24 * 60 * 60)
    for old_backup in BACKUP_DIR.glob("automation_hub_backup_*.zip"):
        if old_backup.stat().st_mtime < cutoff_date:
            old_backup.unlink()
            print(f"✓ Removed old backup: {old_backup.name}")


if __name__ == "__main__":
    main()
