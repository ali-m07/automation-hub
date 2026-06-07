"""Health check endpoints for monitoring and Kubernetes probes."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from automation_hub.core import db

health_router = APIRouter(tags=["health"])


@health_router.get("/health")
async def health():
    """Simple liveness: app is up. No DB check."""
    return JSONResponse({"status": "ok"})


@health_router.get("/live")
async def live():
    """Liveness probe (e.g. K8s livenessProbe). Returns 200 if process is alive."""
    return JSONResponse({"status": "alive"})


@health_router.get("/ready")
async def ready():
    """Readiness: app can serve traffic (DB reachable). Use for K8s readinessProbe."""
    try:
        conn = db.db_connect(db.get_db_file())
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
    except Exception:
        return JSONResponse(
            {"status": "not ready", "error": "Database unavailable"},
            status_code=503,
        )
    return JSONResponse({"status": "ready"})
