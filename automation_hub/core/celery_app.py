"""Celery application factory for Automation Hub.

Optional: only used when CELERY_BROKER_URL is set and celery is installed.
"""

from __future__ import annotations

import os

_celery_app = None


def is_enabled() -> bool:
    """Return True if Celery broker URL is configured."""
    return bool(os.getenv("CELERY_BROKER_URL", "").strip())


def get_celery_app():
    """Return a singleton Celery app instance, or None if not configured."""
    global _celery_app
    if _celery_app is not None:
        return _celery_app
    if not is_enabled():
        return None
    try:
        from celery import Celery  # type: ignore
    except Exception:
        return None

    broker_url = os.getenv("CELERY_BROKER_URL")
    backend_url = os.getenv("CELERY_RESULT_BACKEND", broker_url)
    app = Celery("automation_hub", broker=broker_url, backend=backend_url)
    # Simple JSON serializer is enough
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_reject_on_worker_lost=True,
        result_expires=86400,
        imports=("automation_hub.tasks",),
    )
    _celery_app = app
    return _celery_app


celery_app = get_celery_app()
