"""Background job processor for processing pending jobs from job_queue.
Supports both internal thread-based worker and optional Celery for distributed processing.
"""

from __future__ import annotations

import json
import os
import time
import threading
from typing import Optional, Any

from automation_hub.core.db import db_connect, get_db_file, utc_now_iso
from automation_hub.core.notifications import create_notification, fire_webhooks
from automation_hub.core import audit

# Try to import Celery support
try:
    from automation_hub.core.celery_app import (
        get_celery_app,
        is_enabled as celery_enabled,
    )

    _celery_available = celery_enabled()
except ImportError:
    _celery_available = False
    get_celery_app = None


class JobProcessor:
    """Processes pending jobs from the job_queue table.
    Uses Celery if available, otherwise falls back to internal thread worker.
    """

    def __init__(self, psd_processor):
        """Initialize job processor with PSD processor instance."""
        self.psd_processor = psd_processor
        self._running = False
        self._thread: Optional[threading.Thread] = None
        celery_requested = os.getenv("USE_CELERY_WORKER", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        self._use_celery = _celery_available and celery_requested
        if self._use_celery or celery_enabled():
            self._setup_celery_tasks()

    def _setup_celery_tasks(self) -> None:
        """Register Celery tasks if Celery is available."""
        if not self._use_celery or not get_celery_app:
            return
        celery_app = get_celery_app()
        if not celery_app:
            return

        @celery_app.task(name="automation_hub.process_creative_job")
        def process_creative_job_task(job_payload_json: str) -> dict:
            """Celery task wrapper for creative job processing."""
            payload = json.loads(job_payload_json)
            return self._process_job_sync(payload)

        self._celery_task = process_creative_job_task

    def start(self) -> None:
        """Start the background worker thread (only if not using Celery)."""
        if self._use_celery:
            # Celery workers run separately, no thread needed
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()

    def enqueue_job(self, job_payload: dict) -> Optional[str]:
        """Enqueue job using Celery if available, otherwise return None for sync processing."""
        if self._use_celery and hasattr(self, "_celery_task"):
            result = self._celery_task.delay(json.dumps(job_payload))
            return result.id
        return None

    def _process_job_sync(self, payload: dict) -> dict:
        """Process a job synchronously (used by both thread and Celery)."""
        try:
            from automation_hub.routers import creative as creative_module
            from automation_hub.services.font_manager import resolve_font

            selected_font = resolve_font(payload.get("font_id"))

            job_id, results, zip_path = creative_module._run_process_core(
                payload["psd_file_id"],
                payload["data_file_id"],
                payload["layer_mapping"],
                payload["filename_fields"],
                payload.get("output_format", "both"),
                payload.get("username"),
                self.psd_processor,
                watermark_config=payload.get("watermark_config"),
                font_path=str(selected_font) if selected_font else None,
            )
            return {
                "job_id": job_id,
                "results": results,
                "zip_file": f"/api/download/{job_id}.zip",
            }
        except Exception as e:
            return {"error": str(e)}

    def stop(self) -> None:
        """Stop the background worker thread."""
        self._running = False

    def _worker_loop(self) -> None:
        """Background thread: process pending jobs from job_queue."""
        db_file = get_db_file()
        while self._running:
            try:
                conn = db_connect(db_file)
                # Ensure the connection waits reasonably if database is locked
                conn.execute("PRAGMA busy_timeout = 3000")
                try:
                    conn.execute("BEGIN EXCLUSIVE")
                    # Use a subquery to select and instantly lock/update a single pending job
                    row = conn.execute(
                        """
                        UPDATE job_queue 
                        SET status = 'processing', updated_at = ?
                        WHERE id = (
                            SELECT id FROM job_queue WHERE status = 'pending' ORDER BY id LIMIT 1
                        )
                        RETURNING id, username, payload_json
                        """,
                        (utc_now_iso(),),
                    ).fetchone()

                    if not row:
                        conn.commit()
                        conn.close()
                        time.sleep(2)
                        continue

                    qid, username, payload_json = (
                        row["id"],
                        row["username"],
                        row["payload_json"],
                    )
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    # If database is locked, just sleep and retry
                    conn.close()
                    time.sleep(1)
                    continue
                finally:
                    try:
                        conn.close()
                    except:
                        pass
                try:
                    payload = json.loads(payload_json)
                    # Import helper from creative router (needs psd_processor)
                    from automation_hub.routers import creative as creative_module
                    from automation_hub.services.font_manager import resolve_font

                    selected_font = resolve_font(payload.get("font_id"))

                    job_id, results, zip_path = creative_module._run_process_core(
                        payload["psd_file_id"],
                        payload["data_file_id"],
                        payload["layer_mapping"],
                        payload["filename_fields"],
                        payload.get("output_format", "both"),
                        payload.get("username"),
                        self.psd_processor,
                        watermark_config=payload.get("watermark_config"),
                        font_path=str(selected_font) if selected_font else None,
                    )
                    result_obj = {
                        "job_id": job_id,
                        "results": results,
                        "zip_file": f"/api/download/{job_id}.zip",
                    }
                    conn = db_connect(db_file)
                    try:
                        conn.execute(
                            "UPDATE job_queue SET status = ?, result_json = ?, updated_at = ? WHERE id = ?",
                            ("completed", json.dumps(result_obj), utc_now_iso(), qid),
                        )
                        conn.commit()
                    finally:
                        conn.close()
                    username = payload.get("username")
                    if username:
                        create_notification(
                            username,
                            "job_done",
                            "Your job is done",
                            f"Creative job #{qid} completed. Download from File Repository.",
                        )
                    fire_webhooks(
                        "job_completed",
                        {
                            "job_id": qid,
                            "username": username,
                            "status": "completed",
                            "zip_file": result_obj.get("zip_file"),
                            "job_type": "creative_psd",
                        },
                    )
                    audit.log_action(
                        username or "system", "job_completed", {"job_id": qid}
                    )
                except Exception as e:
                    conn = db_connect(db_file)
                    try:
                        conn.execute(
                            "UPDATE job_queue SET status = ?, result_json = ?, updated_at = ? WHERE id = ?",
                            (
                                "failed",
                                json.dumps({"error": str(e)}),
                                utc_now_iso(),
                                qid,
                            ),
                        )
                        conn.commit()
                    finally:
                        conn.close()
            except Exception:
                pass
            time.sleep(1)
