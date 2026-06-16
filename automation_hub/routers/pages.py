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

    from automation_hub.projects.ticketing.router import _deadline_state

    return templates.TemplateResponse(
        request=request,
        name=template_path,
        context={
            "request": request,
            "user": user,
            "feedback_nomination_closed": _deadline_state()["is_closed"],
        },
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
    user = auth.get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.get("role") != "admin" and not auth.user_has_module(
        user, "data_tables_manual"
    ):
        return RedirectResponse(url="/summary", status_code=302)
    return _render_page(request, "data/index.html", user=user)


@pages_router.get("/creative", response_class=HTMLResponse, response_model=None)
async def creative_page(request: Request):
    """Creative Studio page."""
    user = auth.get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.get("role") != "admin" and not auth.user_has_module(user, "creative_psd"):
        return RedirectResponse(url="/summary", status_code=302)
    return _render_page(request, "creative/index.html", user=user)


@pages_router.get("/feedback", response_class=HTMLResponse, response_model=None)
async def feedback_page(request: Request):
    """Standalone Feedback dashboard."""
    user = auth.get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    modules = user.get("modules") or []
    if (
        user.get("role") != "admin"
        and "feedback_180" not in modules
        and "feedback" not in modules
    ):
        return RedirectResponse(url="/summary", status_code=302)
    return _render_page(request, "feedback/dashboard.html", user=user)


@pages_router.get("/projects", response_class=HTMLResponse, response_model=None)
async def projects_dashboard(request: Request):
    """Projects & Request Types Dashboard."""
    user = auth.get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    modules = user.get("modules") or []
    if (
        user.get("role") != "admin"
        and "ticketing" not in modules
        and "ticketing_admin" not in modules
    ):
        return RedirectResponse(url="/summary", status_code=302)
    return _render_page(request, "feedback/projects.html", user=user)


@pages_router.get("/projects/admin", response_class=HTMLResponse, response_model=None)
async def projects_admin(request: Request):
    """Projects Configuration & Workflow Admin Panel."""
    user = auth.get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    modules = user.get("modules") or []
    if user.get("role") != "admin" and "ticketing_admin" not in modules:
        return RedirectResponse(url="/projects", status_code=302)
    return _render_page(request, "feedback/admin.html", user=user)


@pages_router.get(
    "/projects/my-requests", response_class=HTMLResponse, response_model=None
)
async def my_requests_page(request: Request):
    """Dedicated URL for the signed-in user's ticket requests."""
    user = auth.get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    modules = user.get("modules") or []
    if (
        user.get("role") != "admin"
        and "ticketing" not in modules
        and "ticketing_admin" not in modules
    ):
        return RedirectResponse(url="/summary", status_code=302)
    return _render_page(request, "feedback/projects.html", user=user)


@pages_router.get(
    "/projects/{project_key}", response_class=HTMLResponse, response_model=None
)
async def project_board(project_key: str, request: Request):
    """Project Details & Kanban Board page."""
    user = auth.get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    modules = user.get("modules") or []
    if (
        user.get("role") != "admin"
        and "ticketing" not in modules
        and "ticketing_admin" not in modules
    ):
        return RedirectResponse(url="/summary", status_code=302)

    from automation_hub.projects.ticketing.router import _load_store, _project_visible

    store = _load_store()
    project = next(
        (
            p
            for p in store.get("projects", [])
            if (p.get("key") or "").upper() == project_key.upper()
            or p.get("id") == project_key
        ),
        None,
    )
    if not project or not _project_visible(project, user):
        return RedirectResponse(url="/projects", status_code=302)

    templates = _get_templates(request)
    if not templates:
        return JSONResponse({"error": "Templates not available"}, status_code=500)
    return templates.TemplateResponse(
        request=request,
        name="feedback/board.html",
        context={"request": request, "user": user, "project_key": project_key},
    )


@pages_router.get(
    "/issues/{ticket_id}", response_class=HTMLResponse, response_model=None
)
async def ticket_detail(ticket_id: str, request: Request):
    """Jira-style Ticket Detail page."""
    user = auth.get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    modules = user.get("modules") or []
    if (
        user.get("role") != "admin"
        and "ticketing" not in modules
        and "ticketing_admin" not in modules
    ):
        return RedirectResponse(url="/summary", status_code=302)

    from automation_hub.projects.ticketing.router import (
        _load_store,
        _ticket_visible,
        _find_ticket_and_project,
    )

    store = _load_store()
    ticket, project = _find_ticket_and_project(store, ticket_id)
    if not ticket or not project or not _ticket_visible(project, ticket, user):
        return RedirectResponse(url="/projects", status_code=302)

    templates = _get_templates(request)
    if not templates:
        return JSONResponse({"error": "Templates not available"}, status_code=500)
    return templates.TemplateResponse(
        request=request,
        name="feedback/issue.html",
        context={"request": request, "user": user, "ticket_id": ticket_id},
    )


@pages_router.get(
    "/feedback/nominate", response_class=HTMLResponse, response_model=None
)
async def evaluator_nomination_page(request: Request):
    """Evaluator Nomination page - for employees to nominate their evaluators."""
    user = auth.get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    modules = user.get("modules") or []
    if (
        user.get("role") != "admin"
        and "feedback_180" not in modules
        and "feedback" not in modules
        and "feedback_180_admin" not in modules
        and "feedback_hrbp" not in modules
    ):
        return RedirectResponse(url="/summary", status_code=302)
    from automation_hub.projects.ticketing.router import (
        _deadline_state,
        _identity_key,
        _load_evaluator_store,
    )

    if _deadline_state()["is_closed"]:
        return RedirectResponse(url="/feedback/my-evaluations", status_code=302)
    user_key = _identity_key(user.get("username", ""))
    active_nomination = next(
        (
            nomination
            for nomination in _load_evaluator_store().get("nominations", [])
            if _identity_key(nomination.get("nominator_username")) == user_key
            and nomination.get("status") != "closed"
            and nomination.get("evaluators")
        ),
        None,
    )
    if active_nomination:
        return RedirectResponse(url="/feedback/my-evaluations", status_code=302)

    templates = _get_templates(request)
    if not templates:
        return JSONResponse({"error": "Templates not available"}, status_code=500)
    return templates.TemplateResponse(
        request=request,
        name="feedback/nominate.html",
        context={
            "request": request,
            "user": user,
            "feedback_nomination_closed": _deadline_state()["is_closed"],
        },
    )


@pages_router.get(
    "/feedback/my-evaluations", response_class=HTMLResponse, response_model=None
)
async def my_evaluations_page(request: Request):
    """History and details of evaluator nominations submitted by the user."""
    user = auth.get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    modules = user.get("modules") or []
    if (
        user.get("role") != "admin"
        and "feedback_180" not in modules
        and "feedback" not in modules
        and "feedback_180_admin" not in modules
        and "feedback_hrbp" not in modules
    ):
        return RedirectResponse(url="/summary", status_code=302)
    from automation_hub.projects.ticketing.router import (
        _deadline_state,
        _get_user_info,
        _identity_key,
        _load_evaluator_store,
    )

    nomination_window = _deadline_state()

    nominations = [
        nomination
        for nomination in _load_evaluator_store().get("nominations", [])
        if _identity_key(nomination.get("nominator_username"))
        == _identity_key(user.get("username", ""))
    ]
    nominations.sort(
        key=lambda item: item.get("submitted_at") or item.get("created_at") or "",
        reverse=True,
    )
    for nomination in nominations:
        has_manager_action = any(
            evaluator.get("status") in {"approved", "rejected"}
            for evaluator in nomination.get("evaluators", [])
        )
        nomination["can_edit"] = (
            not nomination_window["is_closed"]
            and nomination.get("status") == "pending"
            and not has_manager_action
        )
        nomination["has_manager_action"] = has_manager_action
        nomination["is_finished"] = nomination.get("status") == "closed"
        created_at = nomination.get("created_at") or nomination.get("submitted_at")
        if created_at:
            try:
                from datetime import datetime

                nomination["created_display"] = datetime.fromisoformat(
                    created_at.replace("Z", "+00:00")
                ).strftime("%B %d, %Y at %H:%M")
            except (TypeError, ValueError):
                nomination["created_display"] = created_at
        else:
            nomination["created_display"] = "Unknown"
        submitted_at = nomination.get("submitted_at") or nomination.get("created_at")
        if submitted_at:
            try:
                from datetime import datetime

                nomination["submitted_display"] = datetime.fromisoformat(
                    submitted_at.replace("Z", "+00:00")
                ).strftime("%B %d, %Y at %H:%M")
            except (TypeError, ValueError):
                nomination["submitted_display"] = submitted_at
        else:
            nomination["submitted_display"] = "Not submitted"
        nomination["manager_info"] = _get_user_info(
            nomination.get("manager_username", "")
        )
        for evaluator in nomination.get("evaluators", []):
            info = _get_user_info(
                evaluator.get("username") or evaluator.get("email", "")
            )
            for key, value in info.items():
                if value not in (None, "", []):
                    evaluator[key] = value
    total_evaluators = sum(
        len(nomination.get("evaluators", [])) for nomination in nominations
    )

    templates = _get_templates(request)
    if not templates:
        return JSONResponse({"error": "Templates not available"}, status_code=500)
    return templates.TemplateResponse(
        request=request,
        name="feedback/my-evaluations.html",
        context={
            "request": request,
            "user": user,
            "nominations": nominations,
            "total_evaluators": total_evaluators,
            "nomination_window": nomination_window,
            "feedback_nomination_closed": nomination_window["is_closed"],
        },
    )


@pages_router.get(
    "/feedback/nomination-approvals", response_class=HTMLResponse, response_model=None
)
async def nomination_approvals_page(request: Request):
    """Manager Approval page - for managers to approve/reject evaluator nominations."""
    user = auth.get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    modules = user.get("modules") or []
    if (
        user.get("role") != "admin"
        and "feedback_180" not in modules
        and "feedback" not in modules
        and "feedback_180_admin" not in modules
        and "feedback_hrbp" not in modules
    ):
        return RedirectResponse(url="/summary", status_code=302)

    templates = _get_templates(request)
    if not templates:
        return JSONResponse({"error": "Templates not available"}, status_code=500)
    from automation_hub.projects.ticketing.router import _deadline_state

    return templates.TemplateResponse(
        request=request,
        name="feedback/nomination-approvals.html",
        context={
            "request": request,
            "user": user,
            "feedback_nomination_closed": _deadline_state()["is_closed"],
        },
    )


@pages_router.get("/messaging", response_class=HTMLResponse, response_model=None)
async def messaging_page(request: Request):
    """Messaging page."""
    user = auth.get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.get("role") != "admin" and not auth.user_has_module(user, "messaging_send"):
        return RedirectResponse(url="/summary", status_code=302)
    return _render_page(request, "messaging/index.html", user=user)


@pages_router.get("/gallery", response_class=HTMLResponse, response_model=None)
async def gallery_page(request: Request):
    """Gallery/File Repository page."""
    user = auth.get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.get("role") != "admin" and not auth.user_has_module(user, "creative_psd"):
        return RedirectResponse(url="/summary", status_code=302)
    return _render_page(request, "gallery/index.html", user=user)


@pages_router.get("/support", response_class=HTMLResponse, response_model=None)
async def support_page(request: Request):
    """Support/Tickets page."""
    user = auth.get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return _render_page(request, "support/index.html", user=user)


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


@pages_router.get("/api/tickets")
async def get_user_tickets(request: Request):
    """Retrieve support tickets for the current user (or all tickets if admin)."""
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )

    username = user.get("username") or ""
    is_admin = user.get("role") == "admin"

    conn = _db()
    try:
        if is_admin:
            rows = conn.execute(
                "SELECT * FROM tickets ORDER BY created_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tickets WHERE user_email = ? ORDER BY created_at DESC",
                (username,),
            ).fetchall()

        tickets = []
        for r in rows:
            tickets.append(
                {
                    "id": r["id"],
                    "user_email": r["user_email"],
                    "subject": r["subject"],
                    "body": r["body"],
                    "status": r["status"] or "open",
                    "created_at": r["created_at"],
                    "admin_reply": r["admin_reply"],
                    "admin_replied_at": r["admin_replied_at"],
                    "priority": r["priority"] or "medium",
                    "category": r["category"] or "general",
                    "assigned_admin": r["assigned_admin"],
                    "first_response_at": r["first_response_at"],
                    "resolved_at": r["resolved_at"],
                    "comments_json": (
                        json.loads(r["comments_json"] or "[]")
                        if "comments_json" in r
                        else []
                    ),
                }
            )

        return JSONResponse({"success": True, "tickets": tickets})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
    finally:
        conn.close()


@pages_router.post("/api/tickets")
async def create_user_ticket(request: Request):
    """Create a new support ticket."""
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )

    username = user.get("username") or ""

    try:
        body = await request.json()
        subject = (body.get("subject") or "").strip()
        body_text = (body.get("body") or "").strip()
        priority = (body.get("priority") or "medium").strip().lower()
        category = (body.get("category") or "general").strip().lower()

        if not subject or not body_text:
            return JSONResponse(
                {"success": False, "error": "Subject and message are required"},
                status_code=400,
            )

        conn = _db()
        try:
            now = db.utc_now_iso()
            cursor = conn.execute(
                """
                INSERT INTO tickets (user_email, subject, body, status, created_at, priority, category, comments_json)
                VALUES (?, ?, ?, 'open', ?, ?, ?, '[]')
                """,
                (username, subject, body_text, now, priority, category),
            )
            ticket_id = cursor.lastrowid
            conn.commit()

            # Retrieve the newly created ticket to return
            row = conn.execute(
                "SELECT * FROM tickets WHERE id = ?", (ticket_id,)
            ).fetchone()
            ticket = {
                "id": row["id"],
                "user_email": row["user_email"],
                "subject": row["subject"],
                "body": row["body"],
                "status": row["status"] or "open",
                "created_at": row["created_at"],
                "admin_reply": row["admin_reply"],
                "admin_replied_at": row["admin_replied_at"],
                "priority": row["priority"] or "medium",
                "category": row["category"] or "general",
                "assigned_admin": row["assigned_admin"],
                "first_response_at": row["first_response_at"],
                "resolved_at": row["resolved_at"],
                "comments_json": [],
            }
        finally:
            conn.close()

        # Send notification
        _send_ticket_creation_notification(
            request, username, subject, body_text, ticket_id
        )

        return JSONResponse({"success": True, "ticket": ticket})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


def _send_ticket_creation_notification(
    request: Request,
    user_email: str,
    subject: str,
    body_text: str,
    ticket_id: int,
) -> None:
    try:
        from automation_hub.core import notifications as notif
        import os

        config = notif.get_notification_config()
        if not config.get("notify_ticket", True) or not config.get("admin_email"):
            return
        email_svc = getattr(request.app.state, "email_service", None)
        if not email_svc:
            return
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_password = os.getenv("SMTP_PASSWORD", "")
        smtp_server = os.getenv("SMTP_SERVER", "smtp.example.com")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        if not smtp_user or not smtp_password:
            return
        html_body = notif.render_html_template(
            config.get("ticket_html_template", ""),
            {
                "user_email": user_email,
                "subject": subject,
                "body": body_text.replace("\n", "<br>"),
                "ticket_id": ticket_id,
            },
        )
        email_svc.send_notification_email(
            smtp_user,
            smtp_password,
            config.get("admin_email"),
            config.get("ticket_subject", "New support ticket"),
            html_body,
            smtp_server,
            smtp_port,
        )
    except Exception as e:
        print(f"Ticket creation notification failed: {e}")


@pages_router.post("/api/tickets/{ticket_id}/comment")
async def add_support_ticket_comment(ticket_id: int, request: Request):
    """Add a comment/reply to a support ticket."""
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )

    username = user.get("username") or ""
    is_admin = user.get("role") == "admin"

    try:
        body = await request.json()
        comment_text = (body.get("body") or "").strip()
        if not comment_text:
            return JSONResponse(
                {"success": False, "error": "Comment text is required"}, status_code=400
            )

        import secrets

        conn = _db()
        try:
            # Check if ticket exists and user has access
            row = conn.execute(
                "SELECT * FROM tickets WHERE id = ?", (ticket_id,)
            ).fetchone()
            if not row:
                return JSONResponse(
                    {"success": False, "error": "Ticket not found"}, status_code=404
                )

            if not is_admin and row["user_email"] != username:
                return JSONResponse(
                    {"success": False, "error": "Permission denied"}, status_code=403
                )

            comments = json.loads(row["comments_json"] or "[]")
            new_comment = {
                "id": f"comment_{secrets.token_hex(4)}",
                "author": username,
                "body": comment_text,
                "created_at": db.utc_now_iso(),
            }
            comments.append(new_comment)

            now = db.utc_now_iso()
            if is_admin:
                conn.execute(
                    "UPDATE tickets SET admin_reply = ?, admin_replied_at = ?, comments_json = ? WHERE id = ?",
                    (comment_text, now, json.dumps(comments), ticket_id),
                )
            else:
                conn.execute(
                    "UPDATE tickets SET comments_json = ? WHERE id = ?",
                    (json.dumps(comments), ticket_id),
                )
            conn.commit()

            # Create a user notification if this was an admin reply
            if is_admin:
                from automation_hub.core import notifications as notif

                notif.create_notification(
                    row["user_email"],
                    "ticket_reply",
                    "Your ticket got a reply",
                    f"Ticket #{ticket_id}: {row['subject']}",
                )

        finally:
            conn.close()

        return JSONResponse({"success": True, "comment": new_comment})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@pages_router.post("/api/tickets/{ticket_id}/status")
async def update_support_ticket_status(ticket_id: int, request: Request):
    """Update support ticket status."""
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )

    username = user.get("username") or ""
    is_admin = user.get("role") == "admin"

    try:
        body = await request.json()
        status = (body.get("status") or "").strip().lower()
        if status not in ("open", "in_progress", "closed"):
            return JSONResponse(
                {"success": False, "error": "Invalid status"}, status_code=400
            )

        conn = _db()
        try:
            row = conn.execute(
                "SELECT * FROM tickets WHERE id = ?", (ticket_id,)
            ).fetchone()
            if not row:
                return JSONResponse(
                    {"success": False, "error": "Ticket not found"}, status_code=404
                )

            if not is_admin:
                if row["user_email"] != username:
                    return JSONResponse(
                        {"success": False, "error": "Permission denied"},
                        status_code=403,
                    )
                if status == "in_progress":
                    return JSONResponse(
                        {
                            "success": False,
                            "error": "Only admins can set tickets to in_progress",
                        },
                        status_code=403,
                    )

            resolved_at = row["resolved_at"]
            if status == "closed" and not resolved_at:
                resolved_at = db.utc_now_iso()
            elif status != "closed":
                resolved_at = None

            conn.execute(
                "UPDATE tickets SET status = ?, resolved_at = ? WHERE id = ?",
                (status, resolved_at, ticket_id),
            )
            conn.commit()
        finally:
            conn.close()

        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
