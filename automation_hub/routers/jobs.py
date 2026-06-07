# Job queue routes (poll async creative jobs)

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from automation_hub.core import auth, db


def _db():
    return db.db_connect(db.get_db_file())


jobs_router = APIRouter(prefix="/api", tags=["jobs"])


@jobs_router.get("/jobs/{queue_id}")
async def get_job_status(queue_id: int, request: Request):
    """Get status and result of a queued job (current user only)."""
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    conn = _db()
    try:
        row = conn.execute(
            "SELECT id, username, status, result_json, created_at, updated_at FROM job_queue WHERE id = ? AND username = ?",
            (queue_id, user["username"]),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    result = {
        "queue_id": row["id"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if row.get("result_json"):
        try:
            result["result"] = json.loads(row["result_json"])
        except Exception:
            result["result"] = None
    return JSONResponse(result)
