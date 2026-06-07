# File Repository / Gallery routes (per-user)

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from automation_hub.core import auth, db


def _db():
    return db.db_connect(db.get_db_file())


GALLERY_DIR = Path("gallery")
GALLERY_DIR.mkdir(exist_ok=True)


gallery_router = APIRouter(prefix="/api/gallery", tags=["gallery"])


@gallery_router.get("/files")
async def gallery_list_files(
    request: Request,
    q: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
):
    """List gallery files for the current user. Optional filter: q (name), from_date, to_date (ISO)."""
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")

    conn = _db()
    try:
        rows = conn.execute(
            """
            SELECT id, username, file_path, thumbnail_path, display_name, file_size, created_at, job_id
            FROM gallery_files
            WHERE username = ?
            ORDER BY created_at DESC
            """,
            (user["username"],),
        ).fetchall()
    finally:
        conn.close()

    out = []
    qv = (q or "").strip().lower()
    for r in rows:
        display = r.get("display_name") or ""
        created_at = r.get("created_at")
        if qv and qv not in display.lower():
            continue
        if from_date and created_at and created_at < from_date:
            continue
        if to_date and created_at and created_at > to_date:
            continue
        out.append(
            {
                "id": r["id"],
                "display_name": display,
                "file_path": r.get("file_path"),
                "thumbnail_path": r.get("thumbnail_path"),
                "file_size": r.get("file_size"),
                "created_at": created_at,
                "job_id": r.get("job_id"),
            }
        )
    return JSONResponse({"success": True, "files": out})


@gallery_router.get("/thumb/{file_id}")
async def gallery_thumb(file_id: int, request: Request):
    """Serve a thumbnail for a gallery file (current user only)."""
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    conn = _db()
    try:
        row = conn.execute(
            "SELECT id, thumbnail_path FROM gallery_files WHERE id = ? AND username = ?",
            (file_id, user["username"]),
        ).fetchone()
    finally:
        conn.close()
    if not row or not row.get("thumbnail_path"):
        raise HTTPException(status_code=404, detail="Not found")

    path = GALLERY_DIR / row["thumbnail_path"]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")

    # Prevent path traversal
    if not str(path.resolve()).startswith(str(GALLERY_DIR.resolve())):
        raise HTTPException(status_code=404, detail="Not found")

    return FileResponse(path=str(path), filename=path.name)


@gallery_router.get("/download/{file_id}")
async def gallery_download(file_id: int, request: Request):
    """Download a gallery file (current user only)."""
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    conn = _db()
    try:
        row = conn.execute(
            "SELECT id, file_path, display_name FROM gallery_files WHERE id = ? AND username = ?",
            (file_id, user["username"]),
        ).fetchone()
    finally:
        conn.close()
    if not row or not row.get("file_path"):
        raise HTTPException(status_code=404, detail="Not found")

    path = GALLERY_DIR / row["file_path"]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")

    if not str(path.resolve()).startswith(str(GALLERY_DIR.resolve())):
        raise HTTPException(status_code=404, detail="Not found")

    filename = row.get("display_name") or path.name
    return FileResponse(path=str(path), filename=filename)
