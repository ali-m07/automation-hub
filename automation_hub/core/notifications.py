"""Notification config, template render, and webhook utilities."""

from __future__ import annotations

import json
import threading
from typing import Any, Dict, Optional
import urllib.request

from . import db as _db


def render_html_template(template: str, variables: Dict[str, Any]) -> str:
    """Simple template renderer: {{var}} -> value."""
    result = template
    for key, value in variables.items():
        pattern = "{{" + key + "}}"
        result = result.replace(pattern, str(value or ""))
    return result


_DEFAULT = {
    "admin_email": "",
    "notify_signup": False,
    "notify_ticket": False,
    "signup_subject": "New user registration request",
    "signup_html_template": "",
    "ticket_subject": "New support ticket",
    "ticket_html_template": "",
    "notify_ticket_reply": True,
    "ticket_reply_subject": "Your support ticket has been updated",
    "ticket_reply_html_template": "<html><body><h2>Ticket update</h2><p>Subject: {{subject}}</p><p>{{reply}}</p><p>Ticket ID: {{ticket_id}}</p></body></html>",
}


def get_notification_config() -> Dict[str, Any]:
    """Get notification config (singleton row from notifications_config)."""
    conn = _db.db_connect(_db.get_db_file())
    try:
        row = conn.execute(
            "SELECT * FROM notifications_config ORDER BY id LIMIT 1"
        ).fetchone()
        if row:
            return {
                "admin_email": _db.safe_row_get(row, "admin_email") or "",
                "notify_signup": bool(_db.safe_row_get(row, "notify_signup")),
                "notify_ticket": bool(_db.safe_row_get(row, "notify_ticket")),
                "signup_subject": _db.safe_row_get(row, "signup_subject")
                or "New user registration request",
                "signup_html_template": _db.safe_row_get(row, "signup_html_template")
                or "",
                "ticket_subject": _db.safe_row_get(row, "ticket_subject")
                or "New support ticket",
                "ticket_html_template": _db.safe_row_get(row, "ticket_html_template")
                or "",
                "notify_ticket_reply": bool(
                    _db.safe_row_get(row, "notify_ticket_reply", 1)
                ),
                "ticket_reply_subject": _db.safe_row_get(row, "ticket_reply_subject")
                or "Your support ticket has been updated",
                "ticket_reply_html_template": _db.safe_row_get(
                    row, "ticket_reply_html_template"
                )
                or _DEFAULT["ticket_reply_html_template"],
            }
    finally:
        conn.close()
    return _DEFAULT.copy()


def create_notification(
    username: str, ntype: str, title: str, body: Optional[str] = None
) -> None:
    """Create a notification entry in the database."""
    try:
        conn = _db.db_connect(_db.get_db_file())
        try:
            conn.execute(
                "INSERT INTO notifications (username, type, title, body, created_at) VALUES (?,?,?,?,?)",
                (username, ntype, title or "", body, _db.utc_now_iso()),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print(f"Failed to create notification: {e}")


def fire_webhooks(event_type: str, payload: Dict[str, Any]) -> None:
    """Fire webhooks for a given event type (runs in background thread)."""

    def _do_post():
        try:
            conn = _db.db_connect(_db.get_db_file())
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
                        _db.safe_row_get(r, "url"),
                        data=body,
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    urllib.request.urlopen(req, timeout=10)
                except Exception as e:
                    print(f"Webhook POST failed for {_db.safe_row_get(r, 'url')}: {e}")
        except Exception as e:
            print(f"Webhooks fetch failed: {e}")

    threading.Thread(target=_do_post, daemon=True).start()


def send_signup_notification(
    user_email: str,
    first_name: str,
    last_name: str,
    created_at: str,
    email_service,
) -> None:
    """Send signup notification email to admin (if enabled)."""
    import os

    try:
        config = get_notification_config()
        if not config["notify_signup"] or not config["admin_email"]:
            return

        # Get SMTP settings from env or use defaults
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_password = os.getenv("SMTP_PASSWORD", "")
        smtp_server = os.getenv("SMTP_SERVER", "smtp.example.com")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))

        if not smtp_user or not smtp_password:
            print("SMTP credentials not configured, skipping notification")
            return

        html_body = render_html_template(
            config["signup_html_template"],
            {
                "username": user_email,
                "email": user_email,
                "first_name": first_name,
                "last_name": last_name,
                "created_at": created_at,
            },
        )

        email_service.send_notification_email(
            smtp_user,
            smtp_password,
            config["admin_email"],
            config["signup_subject"],
            html_body,
            smtp_server,
            smtp_port,
        )
    except Exception as e:
        print(f"Failed to send signup notification: {str(e)}")
