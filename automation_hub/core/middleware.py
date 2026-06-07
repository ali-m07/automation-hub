"""Middleware and logging utilities for Automation Hub."""

import json
import logging
import os
import uuid
import contextvars
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi.requests import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

_request_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id", default=None
)


class JsonLogFormatter(logging.Formatter):
    """Format log records as JSON with level, message, request_id, and optional extra."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        rid = getattr(record, "request_id", None) or _request_id_ctx.get()
        if rid:
            log_obj["request_id"] = rid
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key not in (
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "exc_info",
                "message",
                "request_id",
                "taskName",
            ):
                if value is not None:
                    log_obj[key] = value
        return json.dumps(log_obj, default=str)


def setup_structured_logging() -> None:
    """Configure root logger to output JSON with request_id when STRUCTURED_LOGGING=1."""
    if os.getenv("STRUCTURED_LOGGING", "").lower() not in ("1", "true", "yes"):
        return
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not root.handlers:
        h = logging.StreamHandler()
        h.setFormatter(JsonLogFormatter())
        root.addHandler(h)


class RequestIdAndLogMiddleware(BaseHTTPMiddleware):
    """Set request_id on each request and log request/response as JSON when structured logging is on."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        _request_id_ctx.set(request_id)
        request.state.request_id = request_id
        start = datetime.now(timezone.utc)
        response = await call_next(request)
        duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

        if os.getenv("STRUCTURED_LOGGING", "").lower() in ("1", "true", "yes"):
            logger = logging.getLogger(__name__)
            log_data = {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 2),
            }
            if response.status_code >= 400:
                logger.warning("Request completed with error", extra=log_data)
            else:
                logger.info("Request completed", extra=log_data)

        response.headers["x-request-id"] = request_id
        return response
