# Download routes (zip outputs, etc.)

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

downloads_router = APIRouter(prefix="/api", tags=["downloads"])


@downloads_router.get("/download/{filename}")
async def download_file(filename: str):
    """Download processed files as zip. Streamed so reverse proxies don't timeout."""
    file_path = OUTPUT_DIR / filename
    try:
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        path_resolved = file_path.resolve()
        base_resolved = OUTPUT_DIR.resolve()
        if not str(path_resolved).startswith(str(base_resolved)):
            raise HTTPException(status_code=404, detail="File not found")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/zip",
        headers={
            # Hint to Nginx: do not buffer this response (stream to client)
            "X-Accel-Buffering": "no",
        },
    )
