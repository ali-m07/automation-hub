# Download routes (zip outputs, etc.)

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from automation_hub.core import auth, db

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)
GALLERY_DIR = Path("gallery")
GALLERY_DIR.mkdir(exist_ok=True)

downloads_router = APIRouter(prefix="/api", tags=["downloads"])


def _db():
    return db.db_connect(db.get_db_file())


def _job_owned_by_user(conn, job_id: str, username: str) -> bool:
    rows = conn.execute(
        """
        SELECT username, result_json
        FROM job_queue
        WHERE job_type = 'creative_psd' AND username = ?
        ORDER BY id DESC
        LIMIT 200
        """,
        (username,),
    ).fetchall()
    for row in rows:
        result_json = row.get("result_json") if hasattr(row, "get") else None
        if not result_json:
            continue
        try:
            result = json.loads(result_json) or {}
        except Exception:
            continue
        if result.get("job_id") == job_id:
            return True
        zip_file = str(result.get("zip_file") or "")
        if zip_file.endswith(f"/{job_id}.zip"):
            return True
    return False


@downloads_router.get("/download/{filename}")
async def download_file(filename: str, request: Request):
    """Download a generated ZIP with user scoping; admins may access all jobs."""
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")

    job_id = filename[:-4] if filename.lower().endswith(".zip") else filename
    conn = _db()
    try:
        if user.get("role") == "admin":
            row = conn.execute(
                """
                SELECT file_path, display_name
                FROM gallery_files
                WHERE job_id = ? AND LOWER(file_path) LIKE '%.zip'
                ORDER BY id DESC
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT file_path, display_name
                FROM gallery_files
                WHERE username = ? AND job_id = ? AND LOWER(file_path) LIKE '%.zip'
                ORDER BY id DESC
                LIMIT 1
                """,
                (user["username"], job_id),
            ).fetchone()
    finally:
        conn.close()

    file_path = None
    download_name = filename

    if row and row.get("file_path"):
        candidate = GALLERY_DIR / row["file_path"]
        try:
            if candidate.is_file():
                path_resolved = candidate.resolve()
                base_resolved = GALLERY_DIR.resolve()
                if str(path_resolved).startswith(str(base_resolved)):
                    file_path = candidate
                    download_name = row.get("display_name") or filename
        except Exception:
            file_path = None

    if file_path is None:
        output_candidate = OUTPUT_DIR / f"{job_id}.zip"
        if not output_candidate.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        if user.get("role") != "admin":
            conn = _db()
            try:
                if not _job_owned_by_user(conn, job_id, user["username"]):
                    raise HTTPException(status_code=404, detail="File not found")
            finally:
                conn.close()
        file_path = output_candidate
        download_name = output_candidate.name

    return FileResponse(
        path=str(file_path),
        filename=download_name,
        media_type="application/zip",
        headers={
            # Hint to Nginx: do not buffer this response (stream to client)
            "X-Accel-Buffering": "no",
        },
    )
