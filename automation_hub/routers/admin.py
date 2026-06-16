# Admin routes: dashboard page + all /api/admin/* endpoints.
# Uses automation_hub.core only (no app import to avoid circular deps).

from __future__ import annotations

import json
import os
import sqlite3
import threading
import urllib.request
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from automation_hub.core import audit, auth, constants, db
from automation_hub.core import pg
from automation_hub.core import sqlserver_tables as sst
from automation_hub.core import notifications as notif
from automation_hub.core.settings import get_upload_limits

try:
    # Optional: only available when database connectors feature is installed
    from automation_hub.services.db_connector import get_sql_connection
except ImportError:  # pragma: no cover

    def get_sql_connection(conn_config: Dict[str, Any]):  # type: ignore
        raise RuntimeError("Database connector service not available (pyodbc missing)")


def _is_project_admin_module(module_key: str) -> bool:
    for module in constants.MODULES:
        if module["key"] == module_key:
            return module.get("access_type") == "admin"
    return module_key.endswith("_admin")


def _db():
    conn = db.db_connect(db.get_db_file())
    return conn


def _create_notification(
    username: str, ntype: str, title: str, body: Optional[str] = None
) -> None:
    try:
        now = db.utc_now_iso()
        conn = _db()
        try:
            conn.execute(
                "INSERT INTO notifications (username, type, title, body, created_at) VALUES (?,?,?,?,?)",
                (username, ntype, title or "", body, now),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print(f"Failed to create notification: {e}")


def _fire_webhooks(event_type: str, payload: Dict[str, Any]) -> None:
    def _do_post():
        try:
            conn = _db()
            try:
                rows = conn.execute(
                    "SELECT id, url FROM webhooks WHERE event_type = ?",
                    (event_type,),
                ).fetchall()
            finally:
                conn.close()
            body = json.dumps({"event": event_type, **payload}).encode("utf-8")
            for r in rows:
                try:
                    req = urllib.request.Request(
                        r["url"],
                        data=body,
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    urllib.request.urlopen(req, timeout=10)
                except Exception as e:
                    print(f"Webhook POST failed for {r['url']}: {e}")
        except Exception as e:
            print(f"Webhooks fetch failed: {e}")

    threading.Thread(target=_do_post, daemon=True).start()


def _send_ticket_reply_notification(
    request: Request,
    user_email: str,
    subject: str,
    reply_text: str,
    ticket_id: int,
) -> None:
    try:
        config = notif.get_notification_config()
        if not config.get("notify_ticket_reply", True):
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
            config.get("ticket_reply_html_template", ""),
            {
                "user_email": user_email,
                "subject": subject,
                "reply": reply_text.replace("\n", "<br>"),
                "ticket_id": ticket_id,
            },
        )
        email_svc.send_notification_email(
            smtp_user,
            smtp_password,
            user_email,
            config.get("ticket_reply_subject", "Your support ticket has been updated"),
            html_body,
            smtp_server,
            smtp_port,
        )
    except Exception as e:
        print(f"Ticket reply notification failed: {e}")


# Page router: GET /admin (HTML)
page_router = APIRouter(tags=["admin"])


ADMIN_SECTIONS = {
    "overview",
    "users",
    "ldap",
    "notifications",
    "upload-limits",
    "data-tables",
    "db-connectors",
    "tickets",
    "audit",
    "webhooks",
    "smtp",
    "diagnostics",
    "feedback-deadline",
}


@page_router.get("/admin", response_class=HTMLResponse)
@page_router.get("/admin/{section}", response_class=HTMLResponse)
async def admin_page(request: Request, section: str = "overview"):
    user = auth.get_current_user(request)
    is_super_admin = user and user.get("role") == "admin"
    is_feedback_admin = (
        user
        and user.get("role") == "project_admin"
        and "feedback_180_admin" in (user.get("modules") or [])
    )
    if not is_super_admin and not is_feedback_admin:
        return RedirectResponse(url="/login", status_code=302)
    templates = getattr(request.app.state, "templates", None)
    if not templates:
        return JSONResponse({"error": "Templates not available"}, status_code=500)
    active_tab = section if section in ADMIN_SECTIONS else "overview"
    if is_feedback_admin:
        active_tab = "feedback-deadline"
    return templates.TemplateResponse(
        request=request,
        name="admin/admin.html",
        context={"request": request, "user": user, "active_tab": active_tab},
    )


# API router: all /api/admin/*
admin_router = APIRouter(prefix="/api/admin", tags=["admin"])


@admin_router.get("/modules")
async def admin_list_modules(request: Request):
    auth.require_admin(request, auth.get_current_user)  # noqa: unused
    return JSONResponse({"success": True, "modules": constants.MODULES})


@admin_router.get("/users")
async def admin_list_users(
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    q: str = Query("", max_length=160),
):
    auth.require_admin(request, auth.get_current_user)
    conn = _db()
    try:
        query = q.strip().lower()
        where = ""
        params: List[Any] = []
        if query:
            where = """
                WHERE LOWER(username) LIKE ? OR LOWER(COALESCE(email, '')) LIKE ?
                   OR LOWER(COALESCE(first_name, '')) LIKE ? OR LOWER(COALESCE(last_name, '')) LIKE ?
                   OR LOWER(COALESCE(department, '')) LIKE ?
            """
            pattern = f"%{query}%"
            params.extend([pattern] * 5)
        total_row = conn.execute(
            f"SELECT COUNT(*) AS c FROM users {where}", params
        ).fetchone()
        total = total_row["c"] if total_row else 0
        rows = conn.execute(
            f"""SELECT username,role,level,modules_json,email,status,first_name,last_name,
                       department,manager_username,created_at,last_login_at
                FROM users {where}
                ORDER BY username LIMIT ? OFFSET ?""",
            [*params, limit, offset],
        ).fetchall()
    finally:
        conn.close()
    users: List[Dict[str, Any]] = []
    for r in rows:
        users.append(
            {
                "username": r["username"],
                "role": r["role"],
                "level": r["level"],
                "modules": auth.user_modules_from_record(r),
                "email": db.safe_row_get(r, "email") or "",
                "status": db.safe_row_get(r, "status") or "active",
                "first_name": db.safe_row_get(r, "first_name") or "",
                "last_name": db.safe_row_get(r, "last_name") or "",
                "department": db.safe_row_get(r, "department") or "",
                "manager_username": db.safe_row_get(r, "manager_username") or "",
                "created_at": db.safe_row_get(r, "created_at") or "",
                "last_login_at": db.safe_row_get(r, "last_login_at") or "",
            }
        )
    return JSONResponse({"success": True, "users": users, "total": total})


@admin_router.post("/users/{username}/approve")
async def admin_approve_user(username: str, request: Request):
    admin = auth.require_admin(request, auth.get_current_user)
    conn = _db()
    try:
        updated = conn.execute(
            "UPDATE users SET status = 'active' WHERE username = ? AND status = 'pending'",
            (username,),
        ).rowcount
        conn.commit()
    finally:
        conn.close()
    if not updated:
        return JSONResponse(
            {"success": False, "error": "User not found or already approved"},
            status_code=404,
        )
    audit.audit_log(
        admin.get("username"), "user_approved", target_type="user", target_id=username
    )
    return JSONResponse({"success": True})


@admin_router.post("/users/{username}/reject")
async def admin_reject_user(username: str, request: Request):
    admin = auth.require_admin(request, auth.get_current_user)
    conn = _db()
    try:
        updated = conn.execute(
            "UPDATE users SET status = 'inactive' WHERE username = ? AND status = 'pending'",
            (username,),
        ).rowcount
        conn.commit()
    finally:
        conn.close()
    if not updated:
        return JSONResponse(
            {"success": False, "error": "User not found or not pending"},
            status_code=404,
        )
    audit.audit_log(
        admin.get("username"), "user_rejected", target_type="user", target_id=username
    )
    return JSONResponse({"success": True})


@admin_router.post("/users/bulk-approve")
async def admin_bulk_approve(request: Request):
    admin = auth.require_admin(request, auth.get_current_user)
    body = await request.json()
    usernames = body.get("usernames") or []
    if not isinstance(usernames, list):
        return JSONResponse(
            {"success": False, "error": "usernames must be a list"}, status_code=400
        )
    approved = 0
    conn = _db()
    try:
        for u in usernames:
            u = (str(u) or "").strip()
            if not u:
                continue
            updated = conn.execute(
                "UPDATE users SET status = 'active' WHERE username = ? AND status = 'pending'",
                (u,),
            ).rowcount
            if updated:
                approved += 1
                audit.audit_log(
                    admin.get("username"),
                    "user_approved",
                    target_type="user",
                    target_id=u,
                )
        conn.commit()
    finally:
        conn.close()
    return JSONResponse({"success": True, "approved": approved})


@admin_router.post("/users/bulk-reject")
async def admin_bulk_reject(request: Request):
    admin = auth.require_admin(request, auth.get_current_user)
    body = await request.json()
    usernames = body.get("usernames") or []
    if not isinstance(usernames, list):
        return JSONResponse(
            {"success": False, "error": "usernames must be a list"}, status_code=400
        )
    rejected = 0
    conn = _db()
    try:
        for u in usernames:
            u = (str(u) or "").strip()
            if not u:
                continue
            updated = conn.execute(
                "UPDATE users SET status = 'inactive' WHERE username = ? AND status = 'pending'",
                (u,),
            ).rowcount
            if updated:
                rejected += 1
                audit.audit_log(
                    admin.get("username"),
                    "user_rejected",
                    target_type="user",
                    target_id=u,
                )
        conn.commit()
    finally:
        conn.close()
    return JSONResponse({"success": True, "rejected": rejected})


@admin_router.post("/users/{username}/logout-all")
async def admin_logout_all_sessions(username: str, request: Request):
    admin = auth.require_admin(request, auth.get_current_user)
    conn = _db()
    try:
        row = conn.execute(
            "SELECT username FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not row:
            return JSONResponse(
                {"success": False, "error": "User not found"}, status_code=404
            )
        conn.execute(
            "UPDATE users SET session_version = COALESCE(session_version, 0) + 1 WHERE username = ?",
            (username,),
        )
        conn.commit()
    finally:
        conn.close()
    audit.audit_log(
        admin.get("username"),
        "logout_all_sessions",
        target_type="user",
        target_id=username,
    )
    return JSONResponse({"success": True})


@admin_router.get("/users/{username}/login-log")
async def admin_user_login_log(username: str, request: Request):
    auth.require_admin(request, auth.get_current_user)
    limit = min(int(request.query_params.get("limit", 20)), 100)
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT id,username,logged_at,ip_address,user_agent FROM login_log WHERE username = ? ORDER BY logged_at DESC LIMIT ?",
            (username, limit),
        ).fetchall()
        # Aggregate stats: total logins and failed attempts
        row_ok = conn.execute(
            "SELECT COUNT(*) AS c, MAX(logged_at) AS last_at FROM login_log WHERE username = ?",
            (username,),
        ).fetchone()
        row_fail = conn.execute(
            "SELECT COUNT(*) AS c, MAX(attempted_at) AS last_at FROM login_fail_log WHERE username = ?",
            (username,),
        ).fetchone()
    finally:
        conn.close()
    entries = [
        {
            "id": r["id"],
            "username": r["username"],
            "logged_at": r["logged_at"] or "",
            "ip_address": r["ip_address"] or "",
            "user_agent": (r["user_agent"] or "")[:200],
        }
        for r in rows
    ]
    stats = {
        "total_success": row_ok["c"] if row_ok else 0,
        "last_success_at": row_ok["last_at"] or "" if row_ok else "",
        "total_failed": row_fail["c"] if row_fail else 0,
        "last_failed_at": row_fail["last_at"] or "" if row_fail else "",
    }
    return JSONResponse({"success": True, "entries": entries, "stats": stats})


@admin_router.get("/audit-log")
async def admin_audit_log(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    username: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
):
    auth.require_admin(request, auth.get_current_user)
    conditions = ["1=1"]
    params: List[Any] = []
    if username and username.strip():
        conditions.append("username = ?")
        params.append(username.strip())
    if action and action.strip():
        conditions.append("action = ?")
        params.append(action.strip())
    if from_date and from_date.strip():
        conditions.append("at >= ?")
        params.append(from_date.strip())
    if to_date and to_date.strip():
        conditions.append("at <= ?")
        params.append(to_date.strip())
    where = " AND ".join(conditions)
    params.extend([limit, offset])
    conn = _db()
    try:
        rows = conn.execute(
            f"SELECT id,at,username,action,target_type,target_id,details_json FROM audit_log WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
    finally:
        conn.close()
    entries = []
    for r in rows:
        details = None
        if r["details_json"]:
            try:
                details = json.loads(r["details_json"])
            except Exception:
                details = r["details_json"]
        entries.append(
            {
                "id": r["id"],
                "at": r["at"] or "",
                "username": r["username"] or "",
                "action": r["action"] or "",
                "target_type": r["target_type"] or "",
                "target_id": r["target_id"] or "",
                "details": details,
            }
        )
    return JSONResponse({"success": True, "entries": entries})


@admin_router.post("/users")
async def admin_create_user(request: Request):
    admin = auth.require_admin(request, auth.get_current_user)
    body = await request.json()
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    first_name = (body.get("first_name") or "").strip()
    last_name = (body.get("last_name") or "").strip()
    role = (body.get("role") or "user").strip()
    level = (body.get("level") or "custom").strip()
    modules = body.get("modules") or []

    email_err = auth.validate_email_username(username)
    if email_err:
        return JSONResponse({"success": False, "error": email_err}, status_code=400)
    username = username.lower()
    email = username

    pw_err = auth.validate_password_strength(password)
    if pw_err:
        return JSONResponse({"success": False, "error": pw_err}, status_code=400)
    if role not in ("admin", "project_admin", "user"):
        return JSONResponse(
            {"success": False, "error": "Invalid role"}, status_code=400
        )
    if not isinstance(modules, list):
        return JSONResponse(
            {"success": False, "error": "Invalid modules"}, status_code=400
        )

    allowed_keys = {m["key"] for m in constants.MODULES}
    modules = [m for m in modules if m in allowed_keys]
    if role == "project_admin" and not any(
        _is_project_admin_module(module) for module in modules
    ):
        return JSONResponse(
            {
                "success": False,
                "error": "Select at least one project administration module",
            },
            status_code=400,
        )
    if role == "admin":
        modules = list(allowed_keys)

    conn = _db()
    try:
        existing = conn.execute(
            "SELECT username FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if existing:
            return JSONResponse(
                {"success": False, "error": "Username already exists"}, status_code=409
            )
        conn.execute(
            "INSERT INTO users(username,password,role,level,modules_json,email,status,first_name,last_name,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                username,
                auth.hash_password(password),
                role,
                level,
                json.dumps(modules),
                email,
                "active",
                first_name,
                last_name,
                db.utc_now_iso(),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    audit.audit_log(
        admin.get("username"), "user_created", target_type="user", target_id=username
    )
    return JSONResponse({"success": True})


@admin_router.post("/users/{username}/reset-password")
async def admin_reset_password(username: str, request: Request):
    auth.require_admin(request, auth.get_current_user)
    body = await request.json()
    new_password = body.get("password") or ""
    pw_err = auth.validate_password_strength(new_password)
    if pw_err:
        return JSONResponse({"success": False, "error": pw_err}, status_code=400)
    conn = _db()
    try:
        updated = conn.execute(
            "UPDATE users SET password = ? WHERE username = ?",
            (auth.hash_password(new_password), username),
        ).rowcount
        conn.commit()
    finally:
        conn.close()
    if not updated:
        return JSONResponse(
            {"success": False, "error": "User not found"}, status_code=404
        )
    return JSONResponse({"success": True})


@admin_router.post("/users/{username}/modules")
async def admin_set_user_modules(username: str, request: Request):
    auth.require_admin(request, auth.get_current_user)
    body = await request.json()
    modules = body.get("modules") or []
    if not isinstance(modules, list):
        return JSONResponse(
            {"success": False, "error": "Invalid modules"}, status_code=400
        )
    allowed_keys = {m["key"] for m in constants.MODULES}
    modules = [m for m in modules if m in allowed_keys]

    conn = _db()
    try:
        row = conn.execute(
            "SELECT role FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not row:
            return JSONResponse(
                {"success": False, "error": "User not found"}, status_code=404
            )
        if row["role"] == "admin":
            modules = list(allowed_keys)
        conn.execute(
            "UPDATE users SET modules_json = ? WHERE username = ?",
            (json.dumps(modules), username),
        )
        conn.commit()
    finally:
        conn.close()

    return JSONResponse({"success": True})


@admin_router.post("/users/{username}/update")
async def admin_update_user(username: str, request: Request):
    admin = auth.require_admin(request, auth.get_current_user)
    body = await request.json()
    first_name = (body.get("first_name") or "").strip()
    last_name = (body.get("last_name") or "").strip()
    role = (body.get("role") or "").strip()
    status = auth.normalize_user_status(body.get("status") or "")
    modules = body.get("modules")

    if role and role not in ("admin", "project_admin", "user"):
        return JSONResponse(
            {"success": False, "error": "Invalid role"}, status_code=400
        )
    if status and status not in ("active", "inactive", "pending"):
        return JSONResponse(
            {"success": False, "error": "Invalid status"}, status_code=400
        )
    if modules is not None and not isinstance(modules, list):
        return JSONResponse(
            {"success": False, "error": "Invalid modules"}, status_code=400
        )
    if modules is not None:
        allowed_keys = {module["key"] for module in constants.MODULES}
        modules = [module for module in modules if module in allowed_keys]
        if role == "project_admin" and not any(
            _is_project_admin_module(module) for module in modules
        ):
            return JSONResponse(
                {
                    "success": False,
                    "error": "Select at least one project administration module",
                },
                status_code=400,
            )
        if role == "admin":
            modules = list(allowed_keys)

    if admin.get("username") == username and role and role != "admin":
        return JSONResponse(
            {"success": False, "error": "You cannot change your own role"},
            status_code=400,
        )

    fields = []
    values: List[Any] = []
    if "first_name" in body:
        fields.append("first_name = ?")
        values.append(first_name)
    if "last_name" in body:
        fields.append("last_name = ?")
        values.append(last_name)
    if "department" in body:
        fields.append("department = ?")
        values.append((body.get("department") or "").strip())
    if "manager_username" in body:
        fields.append("manager_username = ?")
        values.append((body.get("manager_username") or "").strip().lower())
    if role:
        fields.append("role = ?")
        values.append(role)
    if status:
        fields.append("status = ?")
        values.append(status)
    if modules is not None:
        fields.append("modules_json = ?")
        values.append(json.dumps(modules))

    if not fields:
        return JSONResponse(
            {"success": False, "error": "No changes provided"}, status_code=400
        )

    values.append(username)
    conn = _db()
    try:
        updated = conn.execute(
            f"UPDATE users SET {', '.join(fields)} WHERE username = ?",
            tuple(values),
        ).rowcount
        conn.commit()
    finally:
        conn.close()
    if not updated:
        return JSONResponse(
            {"success": False, "error": "User not found"}, status_code=404
        )
    return JSONResponse({"success": True})


@admin_router.post("/users/{username}/change-email")
async def admin_change_email(username: str, request: Request):
    admin = auth.require_admin(request, auth.get_current_user)
    body = await request.json()
    new_email = (body.get("new_email") or "").strip().lower()

    email_err = auth.validate_email_username(new_email)
    if email_err:
        return JSONResponse({"success": False, "error": email_err}, status_code=400)

    if username == admin.get("username"):
        return JSONResponse(
            {
                "success": False,
                "error": "You cannot change your own email while logged in",
            },
            status_code=400,
        )

    conn = _db()
    try:
        old = conn.execute(
            "SELECT username FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not old:
            return JSONResponse(
                {"success": False, "error": "User not found"}, status_code=404
            )
        exists = conn.execute(
            "SELECT username FROM users WHERE username = ?", (new_email,)
        ).fetchone()
        if exists:
            return JSONResponse(
                {"success": False, "error": "Email already exists"}, status_code=409
            )

        conn.execute(
            "UPDATE users SET username = ?, email = ? WHERE username = ?",
            (new_email, new_email, username),
        )
        conn.execute(
            "UPDATE tables_meta SET owner_username = ? WHERE owner_username = ?",
            (new_email, username),
        )
        conn.execute(
            "UPDATE table_grants SET grantee_username = ? WHERE grantee_username = ?",
            (new_email, username),
        )
        conn.commit()
    finally:
        conn.close()

    return JSONResponse({"success": True, "username": new_email})


@admin_router.delete("/users/{username}")
async def admin_delete_user(username: str, request: Request):
    admin = auth.require_admin(request, auth.get_current_user)
    if username == admin.get("username"):
        return JSONResponse(
            {"success": False, "error": "You cannot delete your own account"},
            status_code=400,
        )

    conn = _db()
    try:
        user_row = conn.execute(
            "SELECT role FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not user_row:
            return JSONResponse(
                {"success": False, "error": "User not found"}, status_code=404
            )

        if user_row["role"] == "admin":
            admins = conn.execute(
                "SELECT COUNT(*) AS c FROM users WHERE role = 'admin'"
            ).fetchone()
            if admins and int(admins["c"]) <= 1:
                return JSONResponse(
                    {"success": False, "error": "Cannot delete the last admin"},
                    status_code=400,
                )

        conn.execute(
            "DELETE FROM table_grants WHERE grantee_username = ? OR table_id IN (SELECT table_id FROM tables_meta WHERE owner_username = ?)",
            (username, username),
        )
        conn.execute(
            "UPDATE tables_meta SET owner_username = ? WHERE owner_username = ?",
            (admin["username"], username),
        )
        conn.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.commit()
    finally:
        conn.close()

    audit.audit_log(
        admin.get("username"), "user_deleted", target_type="user", target_id=username
    )
    return JSONResponse({"success": True})


@admin_router.get("/webhooks")
async def admin_list_webhooks(
    request: Request,
    limit: int = Query(100, ge=1),
    offset: int = Query(0, ge=0),
):
    auth.require_admin(request, auth.get_current_user)
    conn = _db()
    try:
        total_row = conn.execute("SELECT COUNT(*) AS c FROM webhooks").fetchone()
        total = total_row["c"] if total_row else 0
        rows = conn.execute(
            "SELECT id, url, event_type, created_at FROM webhooks ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    finally:
        conn.close()
    items = [
        {
            "id": r["id"],
            "url": r["url"],
            "event_type": r["event_type"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    return JSONResponse({"success": True, "webhooks": items, "total": total})


@admin_router.post("/webhooks")
async def admin_create_webhook(request: Request, payload: Dict[str, Any]):
    auth.require_admin(request, auth.get_current_user)
    url = (payload.get("url") or "").strip()
    event_type = (payload.get("event_type") or "").strip()
    if not url or not event_type:
        return JSONResponse(
            {"success": False, "error": "url and event_type required"}, status_code=400
        )
    if event_type not in ("job_completed", "ticket_replied"):
        return JSONResponse(
            {
                "success": False,
                "error": "event_type must be job_completed or ticket_replied",
            },
            status_code=400,
        )
    if not url.startswith("http://") and not url.startswith("https://"):
        return JSONResponse(
            {"success": False, "error": "url must start with http:// or https://"},
            status_code=400,
        )
    now = db.utc_now_iso()
    conn = _db()
    try:
        conn.execute(
            "INSERT INTO webhooks (url, event_type, created_at) VALUES (?,?,?)",
            (url, event_type, now),
        )
        conn.commit()
    finally:
        conn.close()
    return JSONResponse({"success": True})


@admin_router.delete("/webhooks/{webhook_id}")
async def admin_delete_webhook(webhook_id: int, request: Request):
    auth.require_admin(request, auth.get_current_user)
    conn = _db()
    try:
        conn.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))
        conn.commit()
    finally:
        conn.close()
    return JSONResponse({"success": True})


@admin_router.get("/stats/summary")
async def admin_stats_summary(request: Request):
    auth.require_admin(request, auth.get_current_user)

    users_stats: Dict[str, Any] = {"total": 0, "active": 0, "pending": 0, "inactive": 0}
    tickets_stats: Dict[str, Any] = {
        "total": 0,
        "open": 0,
        "closed": 0,
        "by_priority": {},
        "by_category": {},
    }
    tables_stats: Dict[str, Any] = {"total": 0}

    conn = _db()
    try:
        row = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
        users_stats["total"] = row["c"] if row else 0
        for st in ("active", "pending", "inactive"):
            r = conn.execute(
                "SELECT COUNT(*) AS c FROM users WHERE status = ?", (st,)
            ).fetchone()
            users_stats[st] = r["c"] if r else 0

        r = conn.execute("SELECT COUNT(*) AS c FROM tickets").fetchone()
        tickets_stats["total"] = r["c"] if r else 0
        for st in ("open", "closed"):
            r2 = conn.execute(
                "SELECT COUNT(*) AS c FROM tickets WHERE status = ?", (st,)
            ).fetchone()
            tickets_stats[st] = r2["c"] if r2 else 0

        for pr_row in conn.execute(
            "SELECT priority, COUNT(*) AS c FROM tickets GROUP BY priority"
        ).fetchall():
            key = (pr_row["priority"] or "medium").lower()
            tickets_stats["by_priority"][key] = pr_row["c"]

        for cat_row in conn.execute(
            "SELECT category, COUNT(*) AS c FROM tickets GROUP BY category"
        ).fetchall():
            key = (cat_row["category"] or "general").lower()
            tickets_stats["by_category"][key] = cat_row["c"]

        r = conn.execute("SELECT COUNT(*) AS c FROM tables_meta").fetchone()
        tables_stats["total"] = r["c"] if r else 0

        # Usage stats: jobs, emails, campaigns
        jobs_stats: Dict[str, Any] = {
            "total": 0,
            "completed": 0,
            "failed": 0,
            "pending": 0,
        }
        jobs_row = conn.execute("SELECT COUNT(*) AS c FROM job_queue").fetchone()
        jobs_stats["total"] = jobs_row["c"] if jobs_row else 0
        for st in ("completed", "failed", "pending"):
            jr = conn.execute(
                "SELECT COUNT(*) AS c FROM job_queue WHERE status = ?", (st,)
            ).fetchone()
            jobs_stats[st] = jr["c"] if jr else 0

        campaigns_stats: Dict[str, Any] = {
            "total": 0,
            "sent": 0,
            "draft": 0,
            "total_emails": 0,
        }
        camp_row = conn.execute("SELECT COUNT(*) AS c FROM email_campaigns").fetchone()
        campaigns_stats["total"] = camp_row["c"] if camp_row else 0
        for st in ("completed", "draft"):
            cr = conn.execute(
                "SELECT COUNT(*) AS c FROM email_campaigns WHERE status = ?", (st,)
            ).fetchone()
            campaigns_stats[st] = cr["c"] if cr else 0
        total_emails_row = conn.execute(
            "SELECT SUM(total_recipients) AS s FROM email_campaigns WHERE total_recipients IS NOT NULL"
        ).fetchone()
        campaigns_stats["total_emails"] = (
            total_emails_row["s"] if total_emails_row and total_emails_row["s"] else 0
        )

        # Data volume (approximate: count gallery files)
        data_stats: Dict[str, Any] = {"gallery_files": 0, "total_size_mb": 0}
        gallery_row = conn.execute("SELECT COUNT(*) AS c FROM gallery_files").fetchone()
        data_stats["gallery_files"] = gallery_row["c"] if gallery_row else 0
        size_row = conn.execute(
            "SELECT SUM(file_size) AS s FROM gallery_files WHERE file_size IS NOT NULL"
        ).fetchone()
        total_bytes = size_row["s"] if size_row and size_row["s"] else 0
        data_stats["total_size_mb"] = (
            round(total_bytes / (1024 * 1024), 2) if total_bytes else 0
        )
    finally:
        conn.close()

    return JSONResponse(
        {
            "success": True,
            "users": users_stats,
            "tickets": tickets_stats,
            "tables": tables_stats,
            "jobs": jobs_stats,
            "campaigns": campaigns_stats,
            "data": data_stats,
        }
    )


@admin_router.get("/notifications/config")
async def admin_get_notification_config(request: Request):
    auth.require_admin(request, auth.get_current_user)
    config = notif.get_notification_config()
    return JSONResponse({"success": True, "config": config})


@admin_router.post("/notifications/config")
async def admin_update_notification_config(request: Request):
    auth.require_admin(request, auth.get_current_user)
    body = await request.json()
    admin_email = (body.get("admin_email") or "").strip()
    notify_signup = bool(body.get("notify_signup", False))
    notify_ticket = bool(body.get("notify_ticket", False))
    notify_ticket_reply = bool(body.get("notify_ticket_reply", False))
    signup_subject = (body.get("signup_subject") or "").strip()
    signup_html_template = body.get("signup_html_template") or ""
    ticket_subject = (body.get("ticket_subject") or "").strip()
    ticket_html_template = body.get("ticket_html_template") or ""
    ticket_reply_subject = (body.get("ticket_reply_subject") or "").strip()
    ticket_reply_html_template = body.get("ticket_reply_html_template") or ""

    if admin_email and "@" not in admin_email:
        return JSONResponse(
            {"success": False, "error": "Invalid admin email"}, status_code=400
        )

    conn = _db()
    try:
        existing = conn.execute(
            "SELECT id FROM notifications_config LIMIT 1"
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE notifications_config SET
                    admin_email = ?, notify_signup = ?, notify_ticket = ?, notify_ticket_reply = ?,
                    signup_subject = ?, signup_html_template = ?, ticket_subject = ?, ticket_html_template = ?,
                    ticket_reply_subject = ?, ticket_reply_html_template = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    admin_email,
                    1 if notify_signup else 0,
                    1 if notify_ticket else 0,
                    1 if notify_ticket_reply else 0,
                    signup_subject,
                    signup_html_template,
                    ticket_subject,
                    ticket_html_template,
                    ticket_reply_subject,
                    ticket_reply_html_template,
                    db.utc_now_iso(),
                    existing["id"],
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO notifications_config(
                    admin_email, notify_signup, notify_ticket, notify_ticket_reply,
                    signup_subject, signup_html_template, ticket_subject, ticket_html_template,
                    ticket_reply_subject, ticket_reply_html_template, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    admin_email,
                    1 if notify_signup else 0,
                    1 if notify_ticket else 0,
                    1 if notify_ticket_reply else 0,
                    signup_subject,
                    signup_html_template,
                    ticket_subject,
                    ticket_html_template,
                    ticket_reply_subject,
                    ticket_reply_html_template,
                    db.utc_now_iso(),
                ),
            )
        conn.commit()
    finally:
        conn.close()

    return JSONResponse({"success": True})


@admin_router.get("/settings/upload-limits")
async def admin_get_upload_limits(request: Request):
    auth.require_admin(request, auth.get_current_user)
    max_bytes, max_files = get_upload_limits()
    max_mb = max_bytes // (1024 * 1024)
    return JSONResponse(
        {"success": True, "max_upload_mb": max_mb, "max_files_per_request": max_files}
    )


@admin_router.post("/settings/upload-limits")
async def admin_update_upload_limits(request: Request):
    auth.require_admin(request, auth.get_current_user)
    body = await request.json()
    max_mb = body.get("max_upload_mb")
    max_files = body.get("max_files_per_request")
    if max_mb is not None:
        max_mb = int(max_mb)
        max_mb = max(1, min(max_mb, 10 * 1024))
        conn = _db()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                ("max_upload_mb", str(max_mb)),
            )
            conn.commit()
        finally:
            conn.close()
    if max_files is not None:
        max_files = int(max_files)
        max_files = max(1, min(max_files, 1000))
        conn = _db()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                ("max_files_per_request", str(max_files)),
            )
            conn.commit()
        finally:
            conn.close()
    details = {}
    if max_mb is not None:
        details["max_upload_mb"] = max_mb
    if max_files is not None:
        details["max_files_per_request"] = max_files
    if details:
        audit.audit_log(
            (auth.get_current_user(request) or {}).get("username"),
            "upload_limits_updated",
            details=details,
        )
    return JSONResponse({"success": True})


@admin_router.get("/auth/config")
async def admin_get_auth_config(request: Request):
    """Return auth/LDAP configuration for UI (admin only)."""
    auth.require_admin(request, auth.get_current_user)
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT key, value FROM app_settings WHERE key IN ("
            "'auth_mode','ldap_enabled','ldap_server','ldap_port','ldap_use_ssl',"
            "'ldap_servers','ldap_base_dn','ldap_user_base_dn','ldap_group_base_dn',"
            "'ldap_bind_dn','ldap_bind_password','ldap_user_principal','ldap_user_filter',"
            "'ldap_directory_filter','ldap_department_groups_enabled'"
            ")"
        ).fetchall()
    finally:
        conn.close()
    raw = {r["key"]: r["value"] for r in rows}
    config = {
        "auth_mode": raw.get("auth_mode") or "local",  # local | ldap | hybrid
        "ldap_enabled": (raw.get("ldap_enabled") or "0") == "1",
        "ldap_server": raw.get("ldap_server") or "",
        "ldap_servers": raw.get("ldap_servers") or raw.get("ldap_server") or "",
        "ldap_port": int(raw.get("ldap_port") or "389"),
        "ldap_use_ssl": (raw.get("ldap_use_ssl") or "0") == "1",
        "ldap_base_dn": raw.get("ldap_base_dn") or "",
        "ldap_user_base_dn": raw.get("ldap_user_base_dn")
        or raw.get("ldap_base_dn")
        or "",
        "ldap_group_base_dn": raw.get("ldap_group_base_dn") or "",
        "ldap_bind_dn": raw.get("ldap_bind_dn") or "",
        # For security, do not return the bind password to the UI.
        "ldap_bind_password_set": bool(raw.get("ldap_bind_password")),
        "ldap_user_filter": raw.get("ldap_user_filter")
        or "(&(objectClass=user)(sAMAccountName={username}))",
        "ldap_user_principal": raw.get("ldap_user_principal")
        or "{username}@snapp.local",
        "ldap_directory_filter": raw.get("ldap_directory_filter")
        or "(&(objectClass=user)(|(sAMAccountName={query})(displayName={query})(mail={query})))",
        "ldap_department_groups_enabled": (
            raw.get("ldap_department_groups_enabled") or "0"
        )
        == "1",
    }
    return JSONResponse({"success": True, "config": config})


@admin_router.post("/auth/config")
async def admin_update_auth_config(request: Request):
    """Update auth/LDAP configuration from UI."""
    auth.require_admin(request, auth.get_current_user)
    body = await request.json()
    auth_mode = (body.get("auth_mode") or "local").strip()
    if auth_mode not in ("local", "ldap", "hybrid"):
        return JSONResponse(
            {"success": False, "error": "Invalid auth_mode"}, status_code=400
        )
    ldap_enabled = bool(body.get("ldap_enabled", False))
    ldap_server = (body.get("ldap_server") or "").strip()
    ldap_servers = (body.get("ldap_servers") or ldap_server).strip()
    ldap_port = int(body.get("ldap_port") or 389)
    ldap_use_ssl = bool(body.get("ldap_use_ssl", False))
    ldap_base_dn = (body.get("ldap_base_dn") or "").strip()
    ldap_user_base_dn = (body.get("ldap_user_base_dn") or ldap_base_dn).strip()
    ldap_group_base_dn = (body.get("ldap_group_base_dn") or "").strip()
    ldap_bind_dn = (body.get("ldap_bind_dn") or "").strip()
    ldap_bind_password = body.get(
        "ldap_bind_password"
    )  # String or None when the password should remain unchanged.
    ldap_user_filter = (
        body.get("ldap_user_filter") or ""
    ).strip() or "(&(objectClass=user)(sAMAccountName={username}))"
    ldap_user_principal = (
        body.get("ldap_user_principal") or "{username}@snapp.local"
    ).strip()
    ldap_directory_filter = (
        body.get("ldap_directory_filter")
        or "(&(objectClass=user)(|(sAMAccountName={query})(displayName={query})(mail={query})))"
    ).strip()
    ldap_department_groups_enabled = bool(
        body.get("ldap_department_groups_enabled", False)
    )

    # Persist the values in app_settings.
    conn = _db()
    try:

        def _set(key: str, value: str) -> None:
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                (key, value),
            )

        _set("auth_mode", auth_mode)
        _set("ldap_enabled", "1" if ldap_enabled else "0")
        _set("ldap_server", ldap_server)
        _set("ldap_servers", ldap_servers)
        _set("ldap_port", str(ldap_port))
        _set("ldap_use_ssl", "1" if ldap_use_ssl else "0")
        _set("ldap_base_dn", ldap_base_dn)
        _set("ldap_user_base_dn", ldap_user_base_dn)
        _set("ldap_group_base_dn", ldap_group_base_dn)
        _set("ldap_bind_dn", ldap_bind_dn)
        if ldap_bind_password is not None:
            # An empty string explicitly clears the stored bind password.
            _set("ldap_bind_password", ldap_bind_password)
        _set("ldap_user_filter", ldap_user_filter)
        _set("ldap_user_principal", ldap_user_principal)
        _set("ldap_directory_filter", ldap_directory_filter)
        _set(
            "ldap_department_groups_enabled",
            "1" if ldap_department_groups_enabled else "0",
        )
        conn.commit()
    finally:
        conn.close()

    audit.audit_log(
        (auth.get_current_user(request) or {}).get("username"),
        "auth_config_updated",
        details={"auth_mode": auth_mode, "ldap_enabled": ldap_enabled},
    )
    return JSONResponse({"success": True})


@admin_router.post("/auth/test")
async def admin_test_ldap(request: Request):
    """Test TCP, service-account bind, and a small user search."""
    auth.require_admin(request, auth.get_current_user)
    from ldap3 import ALL, Connection, Server, SUBTREE

    body = await request.json()
    servers_raw = (body.get("ldap_servers") or body.get("ldap_server") or "").strip()
    servers = [
        item.strip()
        for item in servers_raw.replace("\n", ",").split(",")
        if item.strip()
    ]
    port = int(body.get("ldap_port") or 389)
    use_ssl = bool(body.get("ldap_use_ssl", False))
    bind_user = (body.get("ldap_bind_dn") or "").strip()
    bind_password = body.get("ldap_bind_password")
    if bind_password in (None, ""):
        conn = _db()
        try:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = 'ldap_bind_password'"
            ).fetchone()
            bind_password = db.safe_row_get(row, "value") or ""
        finally:
            conn.close()
    base_dn = (body.get("ldap_user_base_dn") or body.get("ldap_base_dn") or "").strip()
    results = []
    for host in servers:
        result = {"server": host, "port": port, "success": False}
        connection = None
        try:
            server = Server(
                host, port=port, use_ssl=use_ssl, get_info=ALL, connect_timeout=6
            )
            connection = Connection(
                server,
                user=bind_user,
                password=bind_password or "",
                auto_bind=True,
                receive_timeout=8,
            )
            connection.search(
                base_dn,
                "(&(objectClass=user)(mail=*))",
                search_scope=SUBTREE,
                attributes=["displayName", "mail", "department"],
                size_limit=1,
            )
            result.update(
                success=True,
                message="Bind and user search succeeded",
                sample_users=len(connection.entries),
            )
        except Exception as exc:
            result["message"] = str(exc)
        finally:
            if connection:
                connection.unbind()
        results.append(result)
    return JSONResponse(
        {"success": any(item["success"] for item in results), "results": results}
    )


@admin_router.post("/tickets/{ticket_id}/reply")
async def admin_reply_ticket(ticket_id: int, request: Request):
    auth.require_admin(request, auth.get_current_user)
    body = await request.json()
    reply_text = (body.get("reply") or "").strip()

    if not reply_text or len(reply_text) < 5:
        return JSONResponse(
            {"success": False, "error": "Reply must be at least 5 characters"},
            status_code=400,
        )

    conn = _db()
    try:
        ticket = conn.execute(
            "SELECT user_email,subject,status,first_response_at FROM tickets WHERE id = ?",
            (ticket_id,),
        ).fetchone()
        if not ticket:
            return JSONResponse(
                {"success": False, "error": "Ticket not found"}, status_code=404
            )

        now = db.utc_now_iso()
        first_response_at = ticket["first_response_at"] or now
        conn.execute(
            "UPDATE tickets SET admin_reply = ?, admin_replied_at = ?, status = 'closed', first_response_at = ?, resolved_at = ? WHERE id = ?",
            (reply_text, now, first_response_at, now, ticket_id),
        )
        conn.commit()
    finally:
        conn.close()

    admin_user = auth.get_current_user(request)
    audit.audit_log(
        admin_user.get("username") if admin_user else "",
        "ticket_replied",
        target_type="ticket",
        target_id=str(ticket_id),
    )

    try:
        _send_ticket_reply_notification(
            request, ticket["user_email"], ticket["subject"], reply_text, ticket_id
        )
    except Exception as e:
        print(f"Ticket reply notification failed (non-critical): {e}")

    _create_notification(
        ticket["user_email"],
        "ticket_reply",
        "Your ticket got a reply",
        f"Ticket #{ticket_id}: {ticket['subject']}",
    )

    _fire_webhooks(
        "ticket_replied",
        {
            "ticket_id": ticket_id,
            "user_email": ticket["user_email"],
            "subject": ticket["subject"],
        },
    )

    return JSONResponse({"success": True})


@admin_router.post("/tickets/{ticket_id}/status")
async def admin_update_ticket_status(ticket_id: int, request: Request):
    auth.require_admin(request, auth.get_current_user)
    body = await request.json()
    status = (body.get("status") or "").strip()

    if status not in ("open", "in_progress", "closed"):
        return JSONResponse(
            {"success": False, "error": "Invalid status"}, status_code=400
        )

    conn = _db()
    try:
        row = conn.execute(
            "SELECT resolved_at FROM tickets WHERE id = ?",
            (ticket_id,),
        ).fetchone()
        if not row:
            return JSONResponse(
                {"success": False, "error": "Ticket not found"}, status_code=404
            )

        resolved_at = row["resolved_at"]
        if status == "closed" and not resolved_at:
            resolved_at = db.utc_now_iso()

        conn.execute(
            "UPDATE tickets SET status = ?, resolved_at = ? WHERE id = ?",
            (status, resolved_at, ticket_id),
        )
        conn.commit()
    finally:
        conn.close()

    return JSONResponse({"success": True})


@admin_router.post("/tickets/{ticket_id}/assign")
async def admin_assign_ticket(ticket_id: int, request: Request):
    auth.require_admin(request, auth.get_current_user)
    body = await request.json()
    assigned_admin = (body.get("assigned_admin") or "").strip()

    conn = _db()
    try:
        row = conn.execute(
            "SELECT id FROM tickets WHERE id = ?", (ticket_id,)
        ).fetchone()
        if not row:
            return JSONResponse(
                {"success": False, "error": "Ticket not found"}, status_code=404
            )

        val = assigned_admin if assigned_admin else None
        conn.execute(
            "UPDATE tickets SET assigned_admin = ? WHERE id = ?", (val, ticket_id)
        )
        conn.commit()
    finally:
        conn.close()

    admin_user = auth.get_current_user(request)
    audit.audit_log(
        admin_user.get("username") if admin_user else "",
        "ticket_assigned",
        target_type="ticket",
        target_id=str(ticket_id),
        details={"assigned_to": assigned_admin},
    )

    return JSONResponse({"success": True})


@admin_router.post("/db-connectors")
async def create_db_connector(request: Request):
    auth.require_admin(request, auth.get_current_user)
    try:
        body = await request.json()
        name = (body.get("name") or "").strip()
        owner_username = (body.get("owner_username") or "").strip() or None
        server = (body.get("server") or "").strip()
        database = (body.get("database") or "").strip()
        username = (body.get("username") or "").strip()
        password = body.get("password") or ""
        table_name = (body.get("table_name") or "").strip()
        primary_key_columns = body.get("primary_key_columns")
        extra_params = (body.get("extra_params") or "").strip()
        # Only require minimal connection info here; database/table/pks can be configured later.
        if not name or not server or not username:
            return JSONResponse(
                {
                    "success": False,
                    "error": "name, server, username required",
                },
                status_code=400,
            )
        if primary_key_columns is None:
            primary_key_columns = []
        if not isinstance(primary_key_columns, list):
            return JSONResponse(
                {
                    "success": False,
                    "error": "primary_key_columns must be a list",
                },
                status_code=400,
            )
        now = db.utc_now_iso()
        admin_user = auth.get_current_user(request) or {}
        if not owner_username:
            owner_username = admin_user.get("username") or "admin"
        conn = _db()
        try:
            conn.execute(
                """
                INSERT INTO db_connectors (name, owner_username, server, database, username, password, table_name, primary_key_columns, extra_params, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    name,
                    owner_username,
                    server,
                    database,
                    username,
                    password,
                    table_name,
                    json.dumps(primary_key_columns),
                    extra_params or None,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return JSONResponse({"success": True, "message": "Connector created"})
    except sqlite3.IntegrityError as e:
        if "UNIQUE" in str(e):
            return JSONResponse(
                {
                    "success": False,
                    "error": "A connector with this name already exists",
                },
                status_code=400,
            )
        raise
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@admin_router.delete("/db-connectors/{connector_id}")
async def delete_db_connector(connector_id: int, request: Request):
    """Delete a database connector and its grants. Admin only."""
    auth.require_admin(request, auth.get_current_user)
    conn = _db()
    try:
        # First delete grants to avoid orphan rows
        conn.execute(
            "DELETE FROM db_connector_grants WHERE connector_id = ?",
            (connector_id,),
        )
        # Then delete the connector itself
        cur = conn.execute(
            "DELETE FROM db_connectors WHERE id = ?",
            (connector_id,),
        )
        conn.commit()
        if cur.rowcount == 0:
            return JSONResponse(
                {"success": False, "error": "Connector not found"}, status_code=404
            )
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@admin_router.get("/db-connectors/{connector_id}/grants")
async def list_db_connector_grants(connector_id: int, request: Request):
    """List grants for a connector (username + permission). Admin only."""
    auth.require_admin(request, auth.get_current_user)
    conn = _db()
    try:
        rows = conn.execute(
            """
            SELECT grantee_username, permission, created_at
            FROM db_connector_grants
            WHERE connector_id = ?
            ORDER BY grantee_username
            """,
            (connector_id,),
        ).fetchall()
        grants = [
            {
                "username": db.safe_row_get(r, "grantee_username") or "",
                "permission": db.safe_row_get(r, "permission") or "view",
                "created_at": db.safe_row_get(r, "created_at") or "",
            }
            for r in rows
        ]
        return JSONResponse({"success": True, "grants": grants})
    finally:
        conn.close()


@admin_router.post("/db-connectors/list-databases")
async def admin_list_sql_databases(request: Request):
    """Test connection to SQL Server and list databases for given server/user."""
    auth.require_admin(request, auth.get_current_user)
    try:
        body = await request.json()
        server = (body.get("server") or "").strip()
        username = (body.get("username") or "").strip()
        password = body.get("password") or ""
        extra_params = (body.get("extra_params") or "").strip()
        if not server or not username:
            return JSONResponse(
                {"success": False, "error": "server and username are required"},
                status_code=400,
            )
        # Connect to master (or default) just to enumerate databases
        conn_config = {
            "server": server,
            "database": body.get("database") or "master",
            "username": username,
            "password": password,
            "extra_params": extra_params or "",
        }
        with get_sql_connection(conn_config) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sys.databases WHERE name NOT IN ('master','tempdb','model','msdb') ORDER BY name"
            )
            rows = cursor.fetchall() or []
        databases = [r[0] for r in rows]
        return JSONResponse({"success": True, "databases": databases})
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": f"Connection failed: {e}"}, status_code=500
        )


@admin_router.post("/db-connectors/list-tables")
async def admin_list_sql_tables(request: Request):
    """List tables for a specific database using provided connection info."""
    auth.require_admin(request, auth.get_current_user)
    try:
        body = await request.json()
        server = (body.get("server") or "").strip()
        username = (body.get("username") or "").strip()
        password = body.get("password") or ""
        database = (body.get("database") or "").strip()
        extra_params = (body.get("extra_params") or "").strip()
        if not server or not username or not database:
            return JSONResponse(
                {
                    "success": False,
                    "error": "server, username and database are required",
                },
                status_code=400,
            )
        conn_config = {
            "server": server,
            "database": database,
            "username": username,
            "password": password,
            "extra_params": extra_params or "",
        }
        with get_sql_connection(conn_config) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT TABLE_SCHEMA, TABLE_NAME
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_SCHEMA, TABLE_NAME
                """)
            rows = cursor.fetchall() or []
        tables = []
        for schema, name in rows:
            schema = schema or "dbo"
            full_name = f"[{database}].[{schema}].[{name}]"
            tables.append(
                {
                    "schema": schema,
                    "name": name,
                    "full_name": full_name,
                }
            )
        return JSONResponse({"success": True, "tables": tables})
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": f"List tables failed: {e}"}, status_code=500
        )


@admin_router.get("/data-tables/pending")
async def admin_list_pending_tables(request: Request):
    """List Postgres tables that are pending review/promotion."""
    auth.require_admin(request, auth.get_current_user)
    if not pg.is_enabled():
        return JSONResponse(
            {"success": False, "error": "Postgres not configured"}, status_code=503
        )
    with pg.pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_id, title, owner_username, created_at, updated_at, promote_status, storage_backend
                FROM tables_meta
                WHERE promote_status IN ('pending_review')
                ORDER BY updated_at DESC
                LIMIT 200
                """)
            rows = cur.fetchall() or []
    items = []
    for r in rows:
        items.append(
            {
                "table_id": r[0],
                "title": r[1],
                "owner_username": r[2],
                "created_at": r[3].isoformat() if r[3] else "",
                "updated_at": r[4].isoformat() if r[4] else "",
                "promote_status": r[5],
                "storage_backend": r[6],
            }
        )
    return JSONResponse({"success": True, "tables": items})


@admin_router.post("/data-tables/{table_id}/promote")
async def admin_promote_table(table_id: str, request: Request):
    """
    Promote a Postgres-backed table to SQL Server storage.
    After this, reads/writes will go to SQL Server transparently.
    """
    auth.require_admin(request, auth.get_current_user)
    if not pg.is_enabled():
        return JSONResponse(
            {"success": False, "error": "Postgres not configured"}, status_code=503
        )
    if not sst.is_enabled():
        return JSONResponse(
            {
                "success": False,
                "error": "SQL Server storage not configured (set TABLES_SQLSERVER_CONN_STR)",
            },
            status_code=503,
        )

    # Ensure SQL Server schema exists
    try:
        sst.init_schema()
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": f"SQL Server init failed: {e}"}, status_code=503
        )

    with pg.pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT title, owner_username, storage_backend, promote_status FROM tables_meta WHERE table_id = %s",
                (table_id,),
            )
            meta = cur.fetchone()
            if not meta:
                return JSONResponse(
                    {"success": False, "error": "Table not found"}, status_code=404
                )
            title, owner_username, storage_backend, promote_status = meta
            storage_backend = (storage_backend or "postgres").strip().lower()
            promote_status = (promote_status or "draft").strip().lower()

            if storage_backend == "sqlserver":
                return JSONResponse({"success": True, "message": "Already promoted"})

            # Read Postgres content
            cur.execute(
                "SELECT content FROM tables_data WHERE table_id = %s", (table_id,)
            )
            row = cur.fetchone()
            content = row[0] if row else {"columns": [], "rows": []}

        # Copy to SQL Server
        try:
            sst.upsert_table(
                table_id=table_id,
                owner_username=owner_username,
                title=title,
                content_json=json.dumps(content, ensure_ascii=False),
            )
        except Exception as e:
            # Mark failed (best effort)
            try:
                with conn.cursor() as cur2:
                    cur2.execute(
                        "UPDATE tables_meta SET promote_status = 'failed', updated_at = NOW() WHERE table_id = %s",
                        (table_id,),
                    )
                conn.commit()
            except Exception:
                pass
            return JSONResponse(
                {"success": False, "error": f"Promote failed: {e}"}, status_code=500
            )

        # Switch backend pointer
        with conn.cursor() as cur3:
            cur3.execute(
                """
                UPDATE tables_meta
                SET storage_backend = 'sqlserver', promote_status = 'promoted', updated_at = NOW()
                WHERE table_id = %s
                """,
                (table_id,),
            )
        conn.commit()

    return JSONResponse({"success": True, "message": "Promoted to SQL Server"})


@admin_router.get("/reports/jobs")
async def export_jobs_report(
    request: Request, format: str = Query("csv", regex="^(csv|xlsx)$")
):
    """Export jobs report as CSV or Excel."""
    auth.require_admin(request, auth.get_current_user)
    conn = _db()
    try:
        rows = conn.execute("""
            SELECT id, username, status, created_at, updated_at
            FROM job_queue
            ORDER BY created_at DESC
            LIMIT 10000
            """).fetchall()
    finally:
        conn.close()
    import io
    import pandas as pd

    def generate_export():
        df = pd.DataFrame([db.row_to_dict(r) for r in rows])
        if format == "csv":
            out = io.StringIO()
            df.to_csv(out, index=False)
            return out.getvalue().encode("utf-8"), "text/csv", "jobs_report.csv"
        else:
            out = io.BytesIO()
            with pd.ExcelWriter(out, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Jobs")
            out.seek(0)
            return (
                out.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "jobs_report.xlsx",
            )

    content, media_type, filename = await run_in_threadpool(generate_export)
    from fastapi.responses import Response

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@admin_router.get("/reports/audit")
async def export_audit_report(
    request: Request, format: str = Query("csv", regex="^(csv|xlsx)$")
):
    """Export audit log as CSV or Excel."""
    auth.require_admin(request, auth.get_current_user)
    conn = _db()
    try:
        rows = conn.execute("""
            SELECT username, action, details, ip_address, user_agent, created_at
            FROM audit_log
            ORDER BY created_at DESC
            LIMIT 10000
            """).fetchall()
    finally:
        conn.close()
    import io
    import pandas as pd

    def generate_export():
        df = pd.DataFrame([db.row_to_dict(r) for r in rows])
        if format == "csv":
            out = io.StringIO()
            df.to_csv(out, index=False)
            return out.getvalue().encode("utf-8"), "text/csv", "audit_log.csv"
        else:
            out = io.BytesIO()
            with pd.ExcelWriter(out, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Audit Log")
            out.seek(0)
            return (
                out.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "audit_log.xlsx",
            )

    content, media_type, filename = await run_in_threadpool(generate_export)
    from fastapi.responses import Response

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@admin_router.get("/api-keys")
async def list_api_keys(request: Request):
    """List API keys for current user."""
    auth.require_admin(request, auth.get_current_user)
    user = auth.get_current_user(request)
    username = user.get("username") or ""
    conn = _db()
    try:
        rows = conn.execute(
            """
            SELECT id, name, owner_username, scopes_json, created_at, last_used_at, revoked_at
            FROM api_keys
            WHERE owner_username = ?
            ORDER BY created_at DESC
            """,
            (username,),
        ).fetchall()
    finally:
        conn.close()
    keys = [
        {
            "id": r["id"],
            "name": r["name"],
            "scopes": json.loads(r["scopes_json"] or "[]"),
            "created_at": r["created_at"],
            "last_used_at": r["last_used_at"],
            "revoked": bool(r["revoked_at"]),
        }
        for r in rows
    ]
    return JSONResponse({"success": True, "keys": keys})


@admin_router.post("/api-keys")
async def create_api_key(request: Request):
    """Create a new API key."""
    auth.require_admin(request, auth.get_current_user)
    user = auth.get_current_user(request)
    body = await request.json()
    name = (body.get("name") or "").strip()
    scopes = body.get("scopes") or []
    if not name:
        return JSONResponse(
            {"success": False, "error": "name required"}, status_code=400
        )
    username = user.get("username") or ""
    api_key = auth.generate_api_key()
    key_hash = __import__("hashlib").sha256(api_key.encode()).hexdigest()
    now = db.utc_now_iso()
    conn = _db()
    try:
        conn.execute(
            """
            INSERT INTO api_keys (key_hash, name, owner_username, scopes_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (key_hash, name, username, json.dumps(scopes), now),
        )
        conn.commit()
    finally:
        conn.close()
    # Return key only once
    return JSONResponse({"success": True, "api_key": api_key, "name": name})


@admin_router.delete("/api-keys/{key_id}")
async def revoke_api_key(key_id: int, request: Request):
    """Revoke an API key."""
    auth.require_admin(request, auth.get_current_user)
    user = auth.get_current_user(request)
    username = user.get("username") or ""
    conn = _db()
    try:
        conn.execute(
            "UPDATE api_keys SET revoked_at = ? WHERE id = ? AND owner_username = ?",
            (db.utc_now_iso(), key_id, username),
        )
        conn.commit()
    finally:
        conn.close()
    return JSONResponse({"success": True})
