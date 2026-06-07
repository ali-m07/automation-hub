"""Celery tasks for PSD, email, and file processing."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict

import pandas as pd

from automation_hub.core.celery_app import get_celery_app
from automation_hub.services.job_queue import (
    JobCancelled,
    get_job,
    get_job_secret,
    set_progress,
    update_job,
)

celery_app = get_celery_app()


def _process_psd(queue_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    from automation_hub.routers import creative as creative_module
    from automation_hub.services.font_manager import resolve_font
    from automation_hub.services.psd_processor import PSDProcessor

    set_progress(queue_id, 10, "Loading PSD and data")
    selected_font = resolve_font(payload.get("font_id"))
    set_progress(queue_id, 25, "Rendering PSD outputs")
    job_id, results, _ = creative_module._run_process_core(
        payload["psd_file_id"],
        payload["data_file_id"],
        payload["layer_mapping"],
        payload["filename_fields"],
        payload.get("output_format", "both"),
        payload.get("username"),
        PSDProcessor(),
        watermark_config=payload.get("watermark_config"),
        font_path=str(selected_font) if selected_font else None,
    )
    set_progress(queue_id, 90, "Packaging generated files")
    return {
        "job_id": job_id,
        "results": results,
        "zip_file": f"/api/download/{job_id}.zip",
    }


def _send_emails(queue_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    from automation_hub.services.email_service import EmailService

    data_path = Path(payload["data_path"])
    data = (
        pd.read_csv(data_path)
        if data_path.suffix.lower() == ".csv"
        else pd.read_excel(data_path)
    )

    def progress(done: int, total: int, message: str) -> None:
        percent = 10 + int((done / max(total, 1)) * 85)
        set_progress(queue_id, percent, message)

    set_progress(queue_id, 5, "Reading recipient data")
    smtp_password = get_job_secret(queue_id, "smtp_password")
    if not smtp_password:
        raise RuntimeError("SMTP credential expired or is unavailable")
    result = EmailService().send_bulk_emails(
        payload["email"],
        smtp_password,
        data,
        payload["subject"],
        payload.get("image_folder"),
        payload.get("attached_image_path"),
        payload.get("image_link"),
        payload["to_column"],
        payload.get("img_column"),
        payload.get("cc_columns", []),
        payload.get("smtp_server"),
        payload.get("smtp_port"),
        progress_callback=progress,
    )
    return result


def _process_file(queue_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    source = Path(payload["source"])
    destination = Path(payload["destination"])
    if not source.is_file():
        raise FileNotFoundError(source)
    set_progress(queue_id, 20, "Validating source file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    set_progress(queue_id, 50, "Copying file")
    shutil.copy2(source, destination)
    set_progress(queue_id, 95, "Finalizing file")
    return {"file": str(destination), "size": destination.stat().st_size}


if celery_app:

    @celery_app.task(
        bind=True,
        name="automation_hub.execute_job",
        autoretry_for=(OSError, ConnectionError),
        retry_backoff=True,
        retry_jitter=True,
        max_retries=3,
        acks_late=True,
    )
    def execute_job(self, queue_id: int) -> Dict[str, Any]:
        job = get_job(queue_id)
        if not job:
            return {"error": "Job not found"}
        if job["cancel_requested"] or job["status"] == "cancelled":
            return {"cancelled": True}

        update_job(
            queue_id,
            status="processing",
            attempts=int(job["attempts"] or 0) + 1,
            message="Worker started",
        )
        payload = json.loads(job["payload_json"])
        handlers = {
            "creative_psd": _process_psd,
            "bulk_email": _send_emails,
            "file_copy": _process_file,
        }
        try:
            handler = handlers[job["job_type"]]
            result = handler(queue_id, payload)
            update_job(
                queue_id,
                status="completed",
                progress=100,
                message="Completed",
                result_json=json.dumps(result),
            )
            return result
        except JobCancelled:
            update_job(queue_id, status="cancelled", message="Cancelled by user")
            return {"cancelled": True}
        except Exception as exc:
            if self.request.retries < self.max_retries and isinstance(
                exc, (OSError, ConnectionError)
            ):
                update_job(queue_id, status="retrying", message=str(exc))
                raise
            update_job(
                queue_id,
                status="failed",
                message=str(exc),
                result_json=json.dumps({"error": str(exc)}),
            )
            raise
