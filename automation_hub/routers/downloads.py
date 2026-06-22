# Download routes (zip outputs, etc.)

from __future__ import annotations

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

    if not row or not row.get("file_path"):
        raise HTTPException(status_code=404, detail="File not found")

    file_path = GALLERY_DIR / row["file_path"]
    try:
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        path_resolved = file_path.resolve()
        base_resolved = GALLERY_DIR.resolve()
        if not str(path_resolved).startswith(str(base_resolved)):
            raise HTTPException(status_code=404, detail="File not found")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=str(file_path),
        filename=row.get("display_name") or filename,
        media_type="application/zip",
        headers={
            # Hint to Nginx: do not buffer this response (stream to client)
            "X-Accel-Buffering": "no",
        },
    )
