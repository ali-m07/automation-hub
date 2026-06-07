# Job queue routes (poll async creative jobs)

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from automation_hub.core import auth, db
from automation_hub.services.job_queue import create_job, enqueue_job, request_cancel


def _db():
    return db.db_connect(db.get_db_file())


jobs_router = APIRouter(prefix="/api", tags=["jobs"])


@jobs_router.get("/jobs")
async def list_jobs(request: Request, limit: int = 50):
    """List recent jobs for the current user."""
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    conn = _db()
    try:
        rows = conn.execute(
            """
            SELECT id, job_type, status, progress, message, attempts,
                   max_attempts, created_at, updated_at
            FROM job_queue WHERE username = ?
            ORDER BY id DESC LIMIT ?
            """,
            (user["username"], max(1, min(limit, 100))),
        ).fetchall()
    finally:
        conn.close()
    return JSONResponse({"jobs": [db.row_to_dict(row) for row in rows]})


@jobs_router.get("/jobs/{queue_id}")
async def get_job_status(queue_id: int, request: Request):
    """Get status and result of a queued job (current user only)."""
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    conn = _db()
    try:
        row = conn.execute(
            """
            SELECT id, username, job_type, status, progress, message, attempts,
                   max_attempts, cancel_requested, result_json, created_at, updated_at
            FROM job_queue WHERE id = ? AND username = ?
            """,
            (queue_id, user["username"]),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    result = {
        "queue_id": row["id"],
        "job_type": row["job_type"],
        "status": row["status"],
        "progress": row["progress"],
        "message": row["message"],
        "attempts": row["attempts"],
        "max_attempts": row["max_attempts"],
        "cancel_requested": bool(row["cancel_requested"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if row.get("result_json"):
        try:
            result["result"] = json.loads(row["result_json"])
        except Exception:
            result["result"] = None
    return JSONResponse(result)


@jobs_router.post("/jobs/{queue_id}/cancel")
async def cancel_job(queue_id: int, request: Request):
    """Cancel a pending, retrying, or running job."""
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    conn = _db()
    try:
        row = conn.execute(
            "SELECT id FROM job_queue WHERE id = ? AND username = ?",
            (queue_id, user["username"]),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if not request_cancel(queue_id):
        raise HTTPException(status_code=409, detail="Job is already finished")
    return JSONResponse({"success": True, "job_id": queue_id, "status": "cancelled"})


@jobs_router.post("/jobs/files")
async def queue_file_copy(request: Request):
    """Queue a server-side file copy within uploads and outputs."""
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    body = await request.json()
    source_name = Path(str(body.get("source", ""))).name
    destination_name = Path(str(body.get("destination", ""))).name
    if not source_name or not destination_name:
        raise HTTPException(status_code=400, detail="source and destination required")
    source = Path("uploads") / source_name
    destination = Path("outputs") / destination_name
    if not source.is_file():
        raise HTTPException(status_code=404, detail="Source file not found")
    queue_id = create_job(
        user["username"],
        "file_copy",
        {"source": str(source), "destination": str(destination)},
    )
    try:
        enqueue_job(queue_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return JSONResponse({"success": True, "job_id": queue_id}, status_code=202)
