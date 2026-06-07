"""Persistent Celery-backed job queue helpers."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from automation_hub.core import db

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


class JobCancelled(Exception):
    """Raised when a queued job has been cancelled."""


def create_job(
    username: str,
    job_type: str,
    payload: Dict[str, Any],
    max_attempts: int = 3,
) -> int:
    now = db.utc_now_iso()
    conn = db.db_connect(db.get_db_file())
    try:
        conn.execute(
            """
            INSERT INTO job_queue (
                username, job_type, status, progress, message, attempts,
                max_attempts, cancel_requested, payload_json, created_at, updated_at
            ) VALUES (?, ?, 'pending', 0, 'Queued', 0, ?, 0, ?, ?, ?)
            """,
            (username, job_type, max_attempts, json.dumps(payload), now, now),
        )
        row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
        conn.commit()
        return int(row["id"])
    finally:
        conn.close()


def get_job(queue_id: int) -> Optional[Dict[str, Any]]:
    conn = db.db_connect(db.get_db_file())
    try:
        row = conn.execute(
            "SELECT * FROM job_queue WHERE id = ?", (queue_id,)
        ).fetchone()
        return db.row_to_dict(row) if row else None
    finally:
        conn.close()


def update_job(queue_id: int, **values: Any) -> None:
    allowed = {
        "status",
        "progress",
        "message",
        "celery_task_id",
        "attempts",
        "cancel_requested",
        "result_json",
    }
    updates = {key: value for key, value in values.items() if key in allowed}
    if not updates:
        return
    updates["updated_at"] = db.utc_now_iso()
    assignments = ", ".join(f"{key} = ?" for key in updates)
    conn = db.db_connect(db.get_db_file())
    try:
        conn.execute(
            f"UPDATE job_queue SET {assignments} WHERE id = ?",
            (*updates.values(), queue_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_progress(queue_id: int, progress: int, message: str) -> None:
    job = get_job(queue_id)
    if not job or job["status"] in TERMINAL_STATUSES:
        return
    if job["cancel_requested"]:
        raise JobCancelled("Job cancelled by user")
    update_job(
        queue_id,
        status="processing",
        progress=max(0, min(99, int(progress))),
        message=message,
    )


def enqueue_job(queue_id: int) -> str:
    from automation_hub.core.celery_app import get_celery_app

    celery_app = get_celery_app()
    if celery_app is None:
        raise RuntimeError("Celery is not configured")
    result = celery_app.send_task("automation_hub.execute_job", args=[queue_id])
    update_job(queue_id, celery_task_id=result.id)
    return result.id


def store_job_secret(queue_id: int, name: str, value: str) -> None:
    """Store a short-lived job secret in Redis instead of SQLite."""
    import redis

    redis_url = os.getenv("REDIS_URL") or os.getenv("CELERY_BROKER_URL")
    if not redis_url:
        raise RuntimeError("Redis is not configured")
    client = redis.from_url(redis_url, decode_responses=True)
    client.setex(f"automation-hub:job:{queue_id}:secret:{name}", 3600, value)


def get_job_secret(queue_id: int, name: str) -> Optional[str]:
    """Read a short-lived job secret."""
    import redis

    redis_url = os.getenv("REDIS_URL") or os.getenv("CELERY_BROKER_URL")
    if not redis_url:
        return None
    client = redis.from_url(redis_url, decode_responses=True)
    return client.get(f"automation-hub:job:{queue_id}:secret:{name}")


def request_cancel(queue_id: int) -> bool:
    job = get_job(queue_id)
    if not job or job["status"] in TERMINAL_STATUSES:
        return False
    update_job(
        queue_id,
        cancel_requested=1,
        status="cancelled",
        message="Cancelled by user",
    )
    task_id = job.get("celery_task_id")
    if task_id:
        from automation_hub.core.celery_app import get_celery_app

        celery_app = get_celery_app()
        if celery_app:
            celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
    return True
