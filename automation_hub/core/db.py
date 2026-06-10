from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .constants import MODULES
from .auth import hash_password
from .settings import DEFAULT_MAX_FILES_PER_REQUEST, DEFAULT_MAX_UPLOAD_MB


class RowDict(dict):
    """Row type returned by our row_factory. Ensures .get() exists (sqlite3.Row doesn't)."""

    __slots__ = ()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def row_to_dict(row):
    """Convert any row (sqlite3.Row, tuple, etc.) to dict. Safe if row is None or already dict."""
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    if hasattr(row, "keys") and hasattr(row, "__getitem__"):
        try:
            return RowDict((k, row[k]) for k in row.keys())
        except Exception:
            pass
    return row


def safe_row_get(row, key, default=None):
    """Get value from a row (dict or sqlite3.Row) without ever calling .get on Row."""
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    if hasattr(row, "__getitem__") and hasattr(row, "keys"):
        try:
            if key in row.keys():
                return row[key]
        except Exception:
            pass
    return default


def get_db_file() -> Path:
    data_dir = Path(os.getenv("APP_DATA_DIR", ".")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "app.db"


def db_connect(db_file: Optional[Path] = None) -> sqlite3.Connection:
    db_file = db_file or get_db_file()
    conn = sqlite3.connect(db_file)

    def _row_factory(cursor, row):
        if row is None:
            return None
        if cursor and cursor.description:
            return RowDict(zip([col[0] for col in cursor.description], row))
        if hasattr(row, "keys") and hasattr(row, "__getitem__"):
            try:
                return RowDict((k, row[k]) for k in row.keys())
            except Exception:
                pass
        return row

    conn.row_factory = _row_factory
    return conn


def init_database() -> None:
    """Initialize database schema and seed default data."""
    db_file = get_db_file()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = db_connect(db_file)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                role TEXT NOT NULL,
                level TEXT NOT NULL
            )
            """)

        # Lightweight migration: add modules_json, email, status, first_name, last_name, created_at if missing
        cols = {
            safe_row_get(r, "name")
            for r in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        if "modules_json" not in cols:
            conn.execute(
                "ALTER TABLE users ADD COLUMN modules_json TEXT NOT NULL DEFAULT '[]'"
            )
        if "email" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
        if "status" not in cols:
            conn.execute(
                "ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"
            )
        if "first_name" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN first_name TEXT")
        if "last_name" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN last_name TEXT")
        if "created_at" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN created_at TEXT")
        if "last_login_at" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN last_login_at TEXT")
        if "session_version" not in cols:
            conn.execute(
                "ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0"
            )
        if "totp_secret" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN totp_secret TEXT")
        if "totp_enabled" not in cols:
            conn.execute(
                "ALTER TABLE users ADD COLUMN totp_enabled INTEGER NOT NULL DEFAULT 0"
            )
        if "auth_provider" not in cols:
            conn.execute(
                "ALTER TABLE users ADD COLUMN auth_provider TEXT NOT NULL DEFAULT 'local'"
            )
        if "external_subject" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN external_subject TEXT")

        # Backfill created_at for existing rows (used for request timestamps)
        now = utc_now_iso()
        conn.execute(
            "UPDATE users SET created_at = ? WHERE created_at IS NULL OR created_at = ''",
            (now,),
        )

        conn.execute("""
            CREATE TABLE IF NOT EXISTS login_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                logged_at TEXT NOT NULL,
                ip_address TEXT,
                user_agent TEXT
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS login_fail_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                attempted_at TEXT NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                reason TEXT
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                token TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                at TEXT NOT NULL,
                username TEXT,
                action TEXT NOT NULL,
                target_type TEXT,
                target_id TEXT,
                details_json TEXT
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tables_meta (
                table_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                owner_username TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_opened_at TEXT
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS table_grants (
                table_id TEXT NOT NULL,
                grantee_username TEXT NOT NULL,
                permission TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (table_id, grantee_username)
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS share_tokens (
                token TEXT PRIMARY KEY,
                table_id TEXT NOT NULL,
                expires_at TEXT,
                created_at TEXT NOT NULL
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT,
                read_at TEXT,
                created_at TEXT NOT NULL
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS table_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_id TEXT NOT NULL,
                version_number INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                content BLOB
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS table_favorites (
                username TEXT NOT NULL,
                table_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (username, table_id)
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS webhooks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                event_type TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """)
        # API Keys for public API access
        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_hash TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                owner_username TEXT NOT NULL,
                scopes_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                last_used_at TEXT,
                revoked_at TEXT
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_email TEXT NOT NULL,
                notify_signup INTEGER NOT NULL DEFAULT 1,
                notify_ticket INTEGER NOT NULL DEFAULT 1,
                signup_subject TEXT NOT NULL DEFAULT 'New user registration request',
                signup_html_template TEXT NOT NULL DEFAULT '<html><body><h2>New user registration</h2><p>User: {{username}}</p><p>Email: {{email}}</p><p>Name: {{first_name}} {{last_name}}</p><p>Requested at: {{created_at}}</p></body></html>',
                ticket_subject TEXT NOT NULL DEFAULT 'New support ticket',
                ticket_html_template TEXT NOT NULL DEFAULT '<html><body><h2>New ticket</h2><p>From: {{user_email}}</p><p>Subject: {{subject}}</p><p>{{body}}</p></body></html>',
                notify_ticket_reply INTEGER NOT NULL DEFAULT 1,
                ticket_reply_subject TEXT NOT NULL DEFAULT 'Your support ticket has been updated',
                ticket_reply_html_template TEXT NOT NULL DEFAULT '<html><body><h2>Ticket update</h2><p>Subject: {{subject}}</p><p>{{reply}}</p><p>Ticket ID: {{ticket_id}}</p></body></html>',
                updated_at TEXT NOT NULL
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                admin_reply TEXT,
                admin_replied_at TEXT,
                priority TEXT NOT NULL DEFAULT 'medium',
                category TEXT NOT NULL DEFAULT 'general',
                assigned_admin TEXT,
                first_response_at TEXT,
                resolved_at TEXT
            )
            """)

        # Lightweight migrations for advanced notifications & tickets
        notif_cols = {
            safe_row_get(c, "name")
            for c in conn.execute("PRAGMA table_info(notifications_config)").fetchall()
        }
        if "notify_ticket_reply" not in notif_cols:
            conn.execute(
                "ALTER TABLE notifications_config ADD COLUMN notify_ticket_reply INTEGER NOT NULL DEFAULT 1"
            )
        if "ticket_reply_subject" not in notif_cols:
            conn.execute(
                "ALTER TABLE notifications_config ADD COLUMN ticket_reply_subject TEXT NOT NULL "
                "DEFAULT 'Your support ticket has been updated'"
            )
        if "ticket_reply_html_template" not in notif_cols:
            conn.execute(
                "ALTER TABLE notifications_config ADD COLUMN ticket_reply_html_template TEXT NOT NULL "
                "DEFAULT '<html><body><h2>Ticket update</h2><p>Subject: {{subject}}</p><p>{{reply}}</p><p>Ticket ID: {{ticket_id}}</p></body></html>'"
            )

        ticket_cols = {
            safe_row_get(c, "name")
            for c in conn.execute("PRAGMA table_info(tickets)").fetchall()
        }
        if "priority" not in ticket_cols:
            conn.execute(
                "ALTER TABLE tickets ADD COLUMN priority TEXT NOT NULL DEFAULT 'medium'"
            )
        if "category" not in ticket_cols:
            conn.execute(
                "ALTER TABLE tickets ADD COLUMN category TEXT NOT NULL DEFAULT 'general'"
            )
        if "assigned_admin" not in ticket_cols:
            conn.execute("ALTER TABLE tickets ADD COLUMN assigned_admin TEXT")
        if "first_response_at" not in ticket_cols:
            conn.execute("ALTER TABLE tickets ADD COLUMN first_response_at TEXT")
        if "resolved_at" not in ticket_cols:
            conn.execute("ALTER TABLE tickets ADD COLUMN resolved_at TEXT")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS db_connectors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                owner_username TEXT,
                server TEXT NOT NULL,
                database TEXT NOT NULL,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                table_name TEXT NOT NULL,
                primary_key_columns TEXT NOT NULL,
                extra_params TEXT,
                created_at TEXT NOT NULL
            )
            """)

        # Lightweight migration: add owner_username if missing (older DBs)
        db_connector_cols = {
            safe_row_get(c, "name")
            for c in conn.execute("PRAGMA table_info(db_connectors)").fetchall()
        }
        if "owner_username" not in db_connector_cols:
            conn.execute("ALTER TABLE db_connectors ADD COLUMN owner_username TEXT")

        # Per-user visibility for connectors (owner + grants)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS db_connector_grants (
                connector_id INTEGER NOT NULL,
                grantee_username TEXT NOT NULL,
                permission TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (connector_id, grantee_username)
            )
            """)
        # Cloud connectors (Google Sheets, Airtable, Notion)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cloud_connectors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                owner_username TEXT NOT NULL,
                config_json TEXT NOT NULL,
                table_id TEXT,
                sync_enabled INTEGER NOT NULL DEFAULT 0,
                sync_schedule TEXT,
                last_synced_at TEXT,
                created_at TEXT NOT NULL
            )
            """)
        # Scheduled sync tasks
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT NOT NULL,
                target_id INTEGER NOT NULL,
                schedule_cron TEXT,
                next_run_at TEXT,
                last_run_at TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS gallery_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                file_path TEXT NOT NULL,
                thumbnail_path TEXT,
                display_name TEXT NOT NULL,
                file_size INTEGER,
                created_at TEXT NOT NULL,
                job_id TEXT
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS psd_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                category TEXT
            )
            """)
        # Marketplace templates (public/shared templates)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS psd_market_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                description TEXT,
                category TEXT,
                tags_json TEXT DEFAULT '[]',
                price REAL DEFAULT 0,
                currency TEXT DEFAULT 'USD',
                thumbnail_path TEXT,
                file_path TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """)
        cols_pt = {
            safe_row_get(r, "name")
            for r in conn.execute("PRAGMA table_info(psd_templates)").fetchall()
        }
        if "category" not in cols_pt:
            conn.execute("ALTER TABLE psd_templates ADD COLUMN category TEXT")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS job_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                job_type TEXT NOT NULL DEFAULT 'creative_psd',
                status TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                message TEXT,
                celery_task_id TEXT,
                attempts INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 3,
                cancel_requested INTEGER NOT NULL DEFAULT 0,
                payload_json TEXT NOT NULL,
                result_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """)
        job_columns = {
            safe_row_get(r, "name")
            for r in conn.execute("PRAGMA table_info(job_queue)").fetchall()
        }
        job_migrations = {
            "job_type": "TEXT NOT NULL DEFAULT 'creative_psd'",
            "progress": "INTEGER NOT NULL DEFAULT 0",
            "message": "TEXT",
            "celery_task_id": "TEXT",
            "attempts": "INTEGER NOT NULL DEFAULT 0",
            "max_attempts": "INTEGER NOT NULL DEFAULT 3",
            "cancel_requested": "INTEGER NOT NULL DEFAULT 0",
        }
        for column, definition in job_migrations.items():
            if column not in job_columns:
                conn.execute(f"ALTER TABLE job_queue ADD COLUMN {column} {definition}")

        # Email campaigns and analytics
        conn.execute("""
            CREATE TABLE IF NOT EXISTS email_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                subject TEXT NOT NULL,
                template_html TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                scheduled_at TEXT,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                sent_at TEXT,
                total_recipients INTEGER DEFAULT 0
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS campaign_recipients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                name TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                sent_at TEXT,
                opened_at TEXT,
                clicked_at TEXT,
                error TEXT,
                FOREIGN KEY (campaign_id) REFERENCES email_campaigns(id) ON DELETE CASCADE
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contact_lists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                owner_username TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                list_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                name TEXT,
                tags TEXT,
                metadata_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (list_id) REFERENCES contact_lists(id) ON DELETE CASCADE
            )
            """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """)
        # User preferences (onboarding seen, language, etc)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                username TEXT PRIMARY KEY,
                has_seen_onboarding INTEGER NOT NULL DEFAULT 0,
                language TEXT NOT NULL DEFAULT 'en',
                updated_at TEXT NOT NULL
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS custom_field_definitions (
                id TEXT PRIMARY KEY,
                field_key TEXT NOT NULL UNIQUE,
                label TEXT NOT NULL,
                field_type TEXT NOT NULL,
                config_json TEXT NOT NULL DEFAULT '{}',
                scope_type TEXT NOT NULL DEFAULT 'global',
                scope_modules_json TEXT NOT NULL DEFAULT '[]',
                visibility_json TEXT NOT NULL DEFAULT '{}',
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workflow_definitions (
                id TEXT PRIMARY KEY,
                workflow_key TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                description TEXT,
                scope_type TEXT NOT NULL DEFAULT 'global',
                scope_modules_json TEXT NOT NULL DEFAULT '[]',
                statuses_json TEXT NOT NULL DEFAULT '[]',
                transitions_json TEXT NOT NULL DEFAULT '[]',
                manage_policy_json TEXT NOT NULL DEFAULT '{}',
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            )
            """)
        app_settings_keys = {
            safe_row_get(r, "key")
            for r in conn.execute("SELECT key FROM app_settings").fetchall()
        }
        if "max_upload_mb" not in app_settings_keys:
            conn.execute(
                "INSERT INTO app_settings (key, value) VALUES (?, ?)",
                (
                    "max_upload_mb",
                    str(int(os.getenv("MAX_UPLOAD_MB", str(DEFAULT_MAX_UPLOAD_MB)))),
                ),
            )
        if "max_files_per_request" not in app_settings_keys:
            conn.execute(
                "INSERT INTO app_settings (key, value) VALUES (?, ?)",
                (
                    "max_files_per_request",
                    str(
                        int(
                            os.getenv(
                                "MAX_FILES_PER_REQUEST",
                                str(DEFAULT_MAX_FILES_PER_REQUEST),
                            )
                        )
                    ),
                ),
            )

        # Initialize notifications config if empty
        existing_config = conn.execute(
            "SELECT id FROM notifications_config LIMIT 1"
        ).fetchone()
        if not existing_config:
            admin_email_default = os.getenv("ADMIN_EMAIL", "")
            conn.execute(
                """
                INSERT INTO notifications_config(
                    admin_email,
                    notify_signup,
                    notify_ticket,
                    notify_ticket_reply,
                    updated_at
                )
                VALUES (?,?,?,?,?)
                """,
                (admin_email_default, 1, 1, 1, utc_now_iso()),
            )

        # Bootstrap an administrator only when both values are explicitly set.
        admin_user = os.getenv("ADMIN_USER", "").strip()
        admin_pass = os.getenv("ADMIN_PASS", "")
        if admin_user and admin_pass:
            conn.execute(
                "INSERT OR IGNORE INTO users(username,password,role,level,status,created_at) VALUES (?,?,?,?,?,?)",
                (
                    admin_user,
                    hash_password(admin_pass),
                    "admin",
                    "system",
                    "active",
                    now,
                ),
            )

        # Ensure modules_json is populated (admin gets everything; others default to empty)
        all_module_keys = [m["key"] for m in MODULES]
        for row in conn.execute(
            "SELECT username,role,modules_json FROM users"
        ).fetchall():
            username = safe_row_get(row, "username")
            role = safe_row_get(row, "role")
            raw = safe_row_get(row, "modules_json") or "[]"
            try:
                parsed = json.loads(raw)
                if not isinstance(parsed, list):
                    parsed = []
            except Exception:
                parsed = []
            if "feedback" in parsed and "feedback_180" not in parsed:
                parsed = [
                    "feedback_180" if key == "feedback" else key for key in parsed
                ]
            desired = all_module_keys if role == "admin" else parsed
            if role != "admin" and not desired:
                desired = []
            if parsed != desired:
                conn.execute(
                    "UPDATE users SET modules_json = ? WHERE username = ?",
                    (json.dumps(desired), username),
                )
        conn.commit()
    finally:
        conn.close()
