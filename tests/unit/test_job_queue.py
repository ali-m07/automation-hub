"""Tests for persistent queued-job state."""

import json

from automation_hub.core import db
from automation_hub.services import job_queue


def test_create_and_update_job(test_settings):
    db.init_database()

    queue_id = job_queue.create_job(
        "worker@example.com",
        "file_copy",
        {"source": "a.txt", "destination": "b.txt"},
        max_attempts=4,
    )
    created = job_queue.get_job(queue_id)

    assert created["job_type"] == "file_copy"
    assert created["status"] == "pending"
    assert created["progress"] == 0
    assert created["max_attempts"] == 4

    job_queue.set_progress(queue_id, 42, "Working")
    updated = job_queue.get_job(queue_id)
    assert updated["status"] == "processing"
    assert updated["progress"] == 42
    assert updated["message"] == "Working"

    job_queue.update_job(
        queue_id,
        status="completed",
        progress=100,
        result_json=json.dumps({"ok": True}),
    )
    completed = job_queue.get_job(queue_id)
    assert completed["status"] == "completed"
    assert completed["progress"] == 100


def test_cancel_pending_job(test_settings):
    db.init_database()
    queue_id = job_queue.create_job("worker@example.com", "creative_psd", {})

    assert job_queue.request_cancel(queue_id) is True
    cancelled = job_queue.get_job(queue_id)
    assert cancelled["status"] == "cancelled"
    assert cancelled["cancel_requested"] == 1
    assert job_queue.request_cancel(queue_id) is False
