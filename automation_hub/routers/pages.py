"""Page routes (home, error pages, module pages)."""

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from automation_hub.core import auth, db
from automation_hub.core import pg

pages_router = APIRouter(tags=["pages"])


def _db():
    return db.db_connect(db.get_db_file())


def _get_templates(request: Request) -> Optional[Jinja2Templates]:
    """Get Jinja2 templates from app state."""
    return getattr(request.app.state, "templates", None)


def _require_auth(request: Request) -> Optional[RedirectResponse]:
    """Check if user is authenticated, return redirect if not."""
    user = auth.get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return None


def _render_page(
    request: Request, template_path: str, user: Optional[dict] = None
) -> HTMLResponse | JSONResponse:
    """Render a page template with authentication check."""
    templates = _get_templates(request)
    if not templates:
        return JSONResponse({"error": "Templates not available"}, status_code=500)

    if user is None:
        redirect = _require_auth(request)
        if redirect:
            return redirect
        user = auth.get_current_user(request)

    return templates.TemplateResponse(
        request=request,
        name=template_path,
        context={"request": request, "user": user},
    )


@pages_router.get("/error", response_class=HTMLResponse, response_model=None)
async def error_page(
    request: Request,
    error: str = Query("An error occurred"),
    request_id: Optional[str] = Query(None),
):
    """Error page with optional Report to admin (sends error + request_id as ticket)."""
    templates = _get_templates(request)
    if not templates:
        return JSONResponse({"error": "Templates not available"}, status_code=500)
    rid = request_id or getattr(request.state, "request_id", None)
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={"request": request, "error": error, "request_id": rid or ""},
    )


@pages_router.get("/", response_class=HTMLResponse)
async def home(request: Request) -> RedirectResponse:
    """Main application page - redirects to summary."""
    redirect = _require_auth(request)
    if redirect:
        return redirect
    return RedirectResponse(url="/summary", status_code=302)


@pages_router.get("/summary", response_class=HTMLResponse, response_model=None)
async def summary_page(request: Request):
    """Summary page."""
    return _render_page(request, "summary/index.html")


@pages_router.get("/data", response_class=HTMLResponse, response_model=None)
async def data_page(request: Request):
    """Data & Connectors page."""
    return _render_page(request, "data/index.html")


@pages_router.get("/creative", response_class=HTMLResponse, response_model=None)
async def creative_page(request: Request):
    """Creative Studio page."""
    return _render_page(request, "creative/index.html")


@pages_router.get("/feedback", response_class=HTMLResponse, response_model=None)
async def feedback_page(request: Request):
    """180 Feedback Studio page."""
    user = auth.get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    modules = user.get("modules") or []
    if (
        user.get("role") != "admin"
        and "feedback_180" not in modules
        and "feedback_180_admin" not in modules
    ):
        return RedirectResponse(url="/summary", status_code=302)
    return _render_page(request, "feedback/index.html", user=user)


@pages_router.get("/messaging", response_class=HTMLResponse, response_model=None)
async def messaging_page(request: Request):
    """Messaging page."""
    return _render_page(request, "messaging/index.html")


@pages_router.get("/gallery", response_class=HTMLResponse, response_model=None)
async def gallery_page(request: Request):
    """Gallery/File Repository page."""
    return _render_page(request, "gallery/index.html")


@pages_router.get("/support", response_class=HTMLResponse, response_model=None)
async def support_page(request: Request):
    """Support/Tickets page."""
    return _render_page(request, "support/index.html")


@pages_router.get("/external-db", response_class=HTMLResponse, response_model=None)
async def external_db_page(request: Request):
    """External database (SQL Server connectors) page."""
    user = auth.get_current_user(request)
    # Require connectors_db module (or admin)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.get("role") != "admin" and not auth.user_has_module(user, "connectors_db"):
        # Redirect users without module back to summary
        return RedirectResponse(url="/summary", status_code=302)
    return _render_page(request, "external/index.html")


@pages_router.get("/shared/{token}", response_class=HTMLResponse, response_model=None)
async def shared_table_page(token: str, request: Request):
    """Public shared table view (read-only)."""
    templates = _get_templates(request)
    if not templates:
        return JSONResponse({"error": "Templates not available"}, status_code=500)
    # The shared_table.html will call /api/data/tables/share/{token} to fetch data
    return templates.TemplateResponse(
        request=request,
        name="data/shared_table.html",
        context={"request": request, "token": token, "table_id": "shared"},
    )


@pages_router.get("/api/summary")
async def api_summary(request: Request):
    """Return summary data for the current user: tables count, last jobs, gallery count, last ticket."""
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )

    username = user.get("username") or ""
    tables_count = 0
    last_jobs: List[Dict[str, Any]] = []
    gallery_count = 0
    last_ticket: Optional[Dict[str, Any]] = None

    conn = None
    try:
        # Tables are stored in Postgres when enabled; otherwise SQLite legacy.
        if pg.is_enabled():
            with pg.pg_connect() as pg_conn:
                with pg_conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT COUNT(DISTINCT table_id) AS c FROM (
                            SELECT table_id FROM tables_meta WHERE owner_username = %s
                            UNION
                            SELECT table_id FROM table_grants WHERE grantee_username = %s
                        ) x
                        """,
                        (username, username),
                    )
                    row = cur.fetchone()
                    tables_count = int((row[0] if row else 0) or 0)
        else:
            conn = _db()
            # Tables: count where user is owner or grantee
            row = conn.execute(
                """
                SELECT COUNT(DISTINCT table_id) AS c FROM (
                    SELECT table_id FROM tables_meta WHERE owner_username = ?
                    UNION
                    SELECT table_id FROM table_grants WHERE grantee_username = ?
                )
                """,
                (username, username),
            ).fetchone()
            tables_count = int(db.safe_row_get(row, "c") or 0)

        # Last 5 creative jobs for user
        if conn is None:
            conn = _db()
        rows = conn.execute(
            """
            SELECT id, username, status, payload_json, result_json, created_at, updated_at
            FROM job_queue WHERE username = ?
            ORDER BY created_at DESC LIMIT 5
            """,
            (username,),
        ).fetchall()
        for r in rows:
            payload = {}
            if r.get("payload_json"):
                try:
                    payload = json.loads(r["payload_json"]) or {}
                except Exception:
                    pass
            result = None
            if r.get("result_json"):
                try:
                    result = json.loads(r["result_json"])
                except Exception:
                    pass
            row_count = len(payload.get("layer_mapping") or [])
            zip_link = None
            if result and result.get("zip_file"):
                zip_link = result.get("zip_file")
            elif result and result.get("job_id"):
                zip_link = f"/api/download/{result.get('job_id')}.zip"
            last_jobs.append(
                {
                    "job_id": r["id"],
                    "status": r["status"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                    "row_count": row_count,
                    "zip_link": zip_link,
                }
            )

        # Gallery count for user
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM gallery_files WHERE username = ?",
            (username,),
        ).fetchone()
        gallery_count = int(db.safe_row_get(row, "c") or 0)

        # Latest ticket for user (tickets use user_email)
        row = conn.execute(
            """
            SELECT id, user_email, subject, status, created_at, admin_replied_at
            FROM tickets WHERE user_email = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (username,),
        ).fetchone()
        if row:
            last_ticket = {
                "id": row["id"],
                "subject": db.safe_row_get(row, "subject") or "",
                "status": db.safe_row_get(row, "status") or "open",
                "created_at": db.safe_row_get(row, "created_at") or "",
                "admin_replied_at": db.safe_row_get(row, "admin_replied_at"),
            }
    finally:
        if conn is not None:
            conn.close()

    return JSONResponse(
        {
            "success": True,
            "tables_count": tables_count,
            "last_jobs": last_jobs,
            "gallery_count": gallery_count,
            "last_ticket": last_ticket,
        }
    )
