# Database connectors routes (Excel upload + sync)

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any, Dict

import pandas as pd
from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import JSONResponse

from automation_hub.core import auth, db
from automation_hub.core.settings import get_upload_limits

try:
    from automation_hub.services.db_connector import (
        sync_excel_to_connector,
        safe_remove as db_safe_remove,
        preview_table_rows,
        export_table_to_csv,
    )
except ImportError:
    sync_excel_to_connector = None
    db_safe_remove = None
    preview_table_rows = None
    export_table_to_csv = None


UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


def _db():
    return db.db_connect(db.get_db_file())


def _check_upload_size(request: Request) -> None:
    max_bytes, _ = get_upload_limits()
    cl = request.headers.get("content-length")
    if cl and int(cl) > max_bytes:
        mb = max_bytes // (1024 * 1024)
        from fastapi import HTTPException

        raise HTTPException(
            status_code=413, detail=f"File too large. Maximum size is {mb} MB."
        )


router = APIRouter(prefix="/api/db-connectors", tags=["connectors"])


def _is_admin(user: Dict[str, Any]) -> bool:
    return bool(user and user.get("role") == "admin")


def _user_can_use_connector(connector_row: Any, user: Dict[str, Any], conn) -> bool:
    """Owner or grant; admin can always use."""
    if not user:
        return False
    if _is_admin(user):
        return True
    owner = (db.safe_row_get(connector_row, "owner_username") or "").strip().lower()
    if owner and owner == (user.get("username") or "").strip().lower():
        return True
    # grant?
    gr = conn.execute(
        "SELECT permission FROM db_connector_grants WHERE connector_id = ? AND grantee_username = ?",
        (db.safe_row_get(connector_row, "id"), user.get("username")),
    ).fetchone()
    return bool(gr)


@router.get("")
@router.get("/")
async def list_db_connectors(request: Request):
    """List available connectors for the current user (owner + grants). Requires connectors_db module."""
    user = auth.require_module(request, "connectors_db", auth.get_current_user)
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT id, name, owner_username, server, database, username, table_name, primary_key_columns, extra_params, created_at "
            "FROM db_connectors ORDER BY id DESC"
        ).fetchall()
        connectors = []
        for r in rows:
            if not _user_can_use_connector(r, user, conn):
                continue
            connectors.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "owner_username": r.get("owner_username"),
                    "server": r["server"],
                    "database": r["database"],
                    "username": r["username"],
                    "table_name": r["table_name"],
                    "primary_key_columns": json.loads(r["primary_key_columns"] or "[]"),
                    "extra_params": r.get("extra_params") or "",
                    "created_at": r["created_at"],
                }
            )
        return JSONResponse({"success": True, "connectors": connectors})
    finally:
        conn.close()


@router.post("")
@router.post("/")
async def create_db_connector_for_user(request: Request):
    """
    Create a connector owned by the current user (private by default).
    Requires connectors_db module.
    """
    user = auth.require_module(request, "connectors_db", auth.get_current_user)
    body: Dict[str, Any] = await request.json()
    name = (body.get("name") or "").strip()
    server = (body.get("server") or "").strip()
    database = (body.get("database") or "").strip()
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    table_name = (body.get("table_name") or "").strip()
    primary_key_columns = body.get("primary_key_columns")
    extra_params = (body.get("extra_params") or "").strip()
    if not name or not server or not database or not table_name:
        return JSONResponse(
            {"success": False, "error": "name, server, database, table_name required"},
            status_code=400,
        )
    if not isinstance(primary_key_columns, list) or not primary_key_columns:
        return JSONResponse(
            {"success": False, "error": "primary_key_columns must be a non-empty list"},
            status_code=400,
        )

    now = db.utc_now_iso()
    conn = _db()
    try:
        conn.execute(
            """
            INSERT INTO db_connectors
            (name, owner_username, server, database, username, password, table_name, primary_key_columns, extra_params, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                name,
                user.get("username"),
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
        return JSONResponse({"success": True, "message": "Connector created"})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.get("/{connector_id}/preview")
async def preview_db_connector(connector_id: int, request: Request, limit: int = 200):
    """Return a read-only preview of rows for a connector's target table."""
    user = auth.require_module(request, "connectors_db", auth.get_current_user)
    if not preview_table_rows:
        return JSONResponse(
            {
                "success": False,
                "error": "Database connector service not available (install pyodbc)",
            },
            status_code=503,
        )
    conn = _db()
    try:
        row = conn.execute(
            "SELECT id, owner_username, server, database, username, password, table_name, extra_params "
            "FROM db_connectors WHERE id = ?",
            (connector_id,),
        ).fetchone()
        if not row:
            return JSONResponse(
                {"success": False, "error": "Connector not found"}, status_code=404
            )
        if not _user_can_use_connector(row, user, conn):
            return JSONResponse(
                {"success": False, "error": "Access denied"}, status_code=403
            )
        conn_config = {
            "server": row["server"],
            "database": row["database"],
            "username": row["username"],
            "password": row["password"],
            "extra_params": row.get("extra_params") or "",
        }
        table_name = row["table_name"]
    finally:
        conn.close()

    try:
        data = preview_table_rows(conn_config, table_name, limit=limit)
    except RuntimeError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": f"Preview failed: {e}"}, status_code=500
        )

    return JSONResponse(
        {"success": True, "columns": data["columns"], "rows": data["rows"]}
    )


@router.get("/{connector_id}/export")
async def export_db_connector(connector_id: int, request: Request):
    """Export full table for a connector as CSV."""
    user = auth.require_module(request, "connectors_db", auth.get_current_user)
    if not export_table_to_csv:
        return JSONResponse(
            {
                "success": False,
                "error": "Database connector service not available (install pyodbc)",
            },
            status_code=503,
        )
    conn = _db()
    try:
        row = conn.execute(
            "SELECT id, owner_username, server, database, username, password, table_name, extra_params "
            "FROM db_connectors WHERE id = ?",
            (connector_id,),
        ).fetchone()
        if not row:
            return JSONResponse(
                {"success": False, "error": "Connector not found"}, status_code=404
            )
        if not _user_can_use_connector(row, user, conn):
            return JSONResponse(
                {"success": False, "error": "Access denied"}, status_code=403
            )
        conn_config = {
            "server": row["server"],
            "database": row["database"],
            "username": row["username"],
            "password": row["password"],
            "extra_params": row.get("extra_params") or "",
        }
        table_name = row["table_name"]
    finally:
        conn.close()

    try:
        result = export_table_to_csv(conn_config, table_name)
    except RuntimeError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": f"Export failed: {e}"}, status_code=500
        )

    from fastapi.responses import Response

    return Response(
        content=result["content"],
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{result["filename"]}"'},
    )


@router.post("/{connector_id}/grants")
async def grant_db_connector_access(connector_id: int, request: Request):
    """Owner/admin can grant access to another user."""
    user = auth.require_module(request, "connectors_db", auth.get_current_user)
    body: Dict[str, Any] = await request.json()
    grantee = (body.get("grantee_username") or "").strip().lower()
    permission = (body.get("permission") or "view").strip().lower()
    if not grantee:
        return JSONResponse(
            {"success": False, "error": "grantee_username required"}, status_code=400
        )
    if permission not in ("view", "edit"):
        return JSONResponse(
            {"success": False, "error": "permission must be view or edit"},
            status_code=400,
        )

    conn = _db()
    try:
        row = conn.execute(
            "SELECT id, owner_username FROM db_connectors WHERE id = ?",
            (connector_id,),
        ).fetchone()
        if not row:
            return JSONResponse(
                {"success": False, "error": "Connector not found"}, status_code=404
            )
        owner = (row.get("owner_username") or "").strip().lower()
        if (
            not _is_admin(user)
            and owner != (user.get("username") or "").strip().lower()
        ):
            return JSONResponse(
                {"success": False, "error": "Only owner/admin can grant access"},
                status_code=403,
            )
        now = db.utc_now_iso()
        conn.execute(
            """
            INSERT OR REPLACE INTO db_connector_grants(connector_id, grantee_username, permission, created_at)
            VALUES (?,?,?,?)
            """,
            (connector_id, grantee, permission, now),
        )
        conn.commit()
        return JSONResponse({"success": True})
    finally:
        conn.close()


@router.delete("/{connector_id}/grants/{grantee_username}")
async def revoke_db_connector_access(
    connector_id: int, grantee_username: str, request: Request
):
    """Owner/admin can revoke access."""
    user = auth.require_module(request, "connectors_db", auth.get_current_user)
    grantee = (grantee_username or "").strip().lower()
    conn = _db()
    try:
        row = conn.execute(
            "SELECT id, owner_username FROM db_connectors WHERE id = ?",
            (connector_id,),
        ).fetchone()
        if not row:
            return JSONResponse(
                {"success": False, "error": "Connector not found"}, status_code=404
            )
        owner = (row.get("owner_username") or "").strip().lower()
        if (
            not _is_admin(user)
            and owner != (user.get("username") or "").strip().lower()
        ):
            return JSONResponse(
                {"success": False, "error": "Only owner/admin can revoke access"},
                status_code=403,
            )
        conn.execute(
            "DELETE FROM db_connector_grants WHERE connector_id = ? AND grantee_username = ?",
            (connector_id, grantee),
        )
        conn.commit()
        return JSONResponse({"success": True})
    finally:
        conn.close()


@router.post("/upload")
async def db_connectors_upload(request: Request, file: UploadFile = File(...)):
    """Upload Excel for DB sync; return sheet names. Requires connectors_db module."""
    _check_upload_size(request)
    auth.require_module(request, "connectors_db", auth.get_current_user)
    if not file.filename or not (file.filename.lower().endswith((".xlsx", ".xls"))):
        return JSONResponse(
            {"success": False, "error": "Excel file (.xlsx, .xls) required"},
            status_code=400,
        )
    try:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        import os
        import shutil

        safe_filename = os.path.basename(file.filename.replace("\\", "/"))
        safe_name = f"db_sync_{secrets.token_hex(8)}_{safe_filename}"
        file_path = UPLOAD_DIR / safe_name
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        with pd.ExcelFile(file_path, engine="openpyxl") as xl:
            sheets = xl.sheet_names
        return JSONResponse({"success": True, "filename": safe_name, "sheets": sheets})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/sync")
async def db_connectors_sync(request: Request):
    """Run Excel-to-SQL sync for a connector. Requires connectors_db module."""
    user = auth.require_module(request, "connectors_db", auth.get_current_user)
    if not sync_excel_to_connector:
        return JSONResponse(
            {
                "success": False,
                "error": "Database connector service not available (install pyodbc)",
            },
            status_code=503,
        )
    try:
        body: Dict[str, Any] = await request.json()
        connector_id = body.get("connector_id")
        filename = (body.get("filename") or "").strip()
        sheet_name = (body.get("sheet_name") or "").strip()
        if not connector_id or not filename or not sheet_name:
            return JSONResponse(
                {
                    "success": False,
                    "error": "connector_id, filename, sheet_name required",
                },
                status_code=400,
            )
        file_path = UPLOAD_DIR / filename
        if not file_path.exists():
            return JSONResponse(
                {"success": False, "error": "Uploaded file not found"}, status_code=404
            )
        conn = _db()
        try:
            row = conn.execute(
                "SELECT id, name, owner_username, server, database, username, password, table_name, primary_key_columns, extra_params "
                "FROM db_connectors WHERE id = ?",
                (connector_id,),
            ).fetchone()
            if not row:
                return JSONResponse(
                    {"success": False, "error": "Connector not found"}, status_code=404
                )
            if not _user_can_use_connector(row, user, conn):
                return JSONResponse(
                    {"success": False, "error": "Access denied"},
                    status_code=403,
                )
        finally:
            conn.close()
        primary_key_columns = json.loads(row["primary_key_columns"] or "[]")
        conn_config = {
            "server": row["server"],
            "database": row["database"],
            "username": row["username"],
            "password": row["password"],
            "extra_params": row.get("extra_params") or "",
        }
        ok = sync_excel_to_connector(
            str(file_path),
            sheet_name,
            conn_config,
            row["table_name"],
            primary_key_columns,
        )
        if db_safe_remove:
            db_safe_remove(str(file_path))
        if ok:
            return JSONResponse(
                {"success": True, "message": "Sync completed successfully"}
            )
            return JSONResponse(
                {"success": False, "error": "Sync failed (check server logs)"},
                status_code=500,
            )
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.get("/cloud")
async def list_cloud_connectors(request: Request):
    """List cloud connectors (Google Sheets, Airtable, Notion)."""
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )
    auth.require_module(request, "data_tables_manual", auth.get_current_user)
    username = user.get("username") or ""
    conn = _db()
    try:
        rows = conn.execute(
            """
            SELECT id, name, type, owner_username, config_json, table_id, sync_enabled, sync_schedule, last_synced_at
            FROM cloud_connectors
            WHERE owner_username = ?
            ORDER BY created_at DESC
            """,
            (username,),
        ).fetchall()
    finally:
        conn.close()
    connectors = [
        {
            "id": r["id"],
            "name": r["name"],
            "type": r["type"],
            "table_id": r["table_id"],
            "sync_enabled": bool(r["sync_enabled"]),
            "sync_schedule": r["sync_schedule"],
            "last_synced_at": r["last_synced_at"],
        }
        for r in rows
    ]
    return JSONResponse({"success": True, "connectors": connectors})


@router.post("/cloud")
async def create_cloud_connector(request: Request):
    """Create a cloud connector."""
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )
    auth.require_module(request, "data_tables_manual", auth.get_current_user)
    body: Dict[str, Any] = await request.json()
    name = (body.get("name") or "").strip()
    connector_type = (body.get("type") or "").strip()
    config = body.get("config") or {}
    table_id = (body.get("table_id") or "").strip()
    if not name or connector_type not in ("google_sheets", "airtable", "notion"):
        return JSONResponse(
            {"success": False, "error": "name and valid type required"}, status_code=400
        )
    username = user.get("username") or ""
    now = db.utc_now_iso()
    conn = _db()
    try:
        conn.execute(
            """
            INSERT INTO cloud_connectors (name, type, owner_username, config_json, table_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, connector_type, username, json.dumps(config), table_id, now),
        )
        row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
        connector_id = row["id"]
        conn.commit()
    finally:
        conn.close()
    return JSONResponse({"success": True, "connector_id": connector_id})


@router.post("/cloud/{connector_id}/sync")
async def sync_cloud_connector(connector_id: int, request: Request):
    """Sync cloud connector (pull or push)."""
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )
    auth.require_module(request, "data_tables_manual", auth.get_current_user)
    body: Dict[str, Any] = await request.json()
    direction = (body.get("direction") or "pull").strip()
    username = user.get("username") or ""
    conn = _db()
    try:
        row = conn.execute(
            "SELECT type, config_json, table_id FROM cloud_connectors WHERE id = ? AND owner_username = ?",
            (connector_id, username),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return JSONResponse(
            {"success": False, "error": "Connector not found"}, status_code=404
        )
    try:
        from automation_hub.services.cloud_connectors import get_connector

        connector = get_connector(row["type"], json.loads(row["config_json"] or "{}"))
        if direction == "pull":
            data = connector.pull_data()
            # Update table in Postgres
            if row["table_id"]:
                import automation_hub.core.pg as pg

                if pg.is_enabled():
                    with pg.pg_connect() as pg_conn:
                        with pg_conn.cursor() as cur:
                            cur.execute(
                                """
                                INSERT INTO tables_data(table_id, content, updated_at)
                                VALUES (%s, %s::jsonb, NOW())
                                ON CONFLICT (table_id) DO UPDATE SET content = EXCLUDED.content, updated_at = NOW()
                                """,
                                (
                                    row["table_id"],
                                    json.dumps({"columns": [], "rows": data}),
                                ),
                            )
                        pg_conn.commit()
            conn = _db()
            try:
                conn.execute(
                    "UPDATE cloud_connectors SET last_synced_at = ? WHERE id = ?",
                    (db.utc_now_iso(), connector_id),
                )
                conn.commit()
            finally:
                conn.close()
            return JSONResponse({"success": True, "rows_pulled": len(data)})
        else:
            return JSONResponse(
                {"success": False, "error": "Push not implemented yet"}, status_code=501
            )
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/cloud/{connector_id}/schedule")
async def schedule_cloud_sync(connector_id: int, request: Request):
    """Schedule automatic sync for cloud connector."""
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )
    auth.require_module(request, "data_tables_manual", auth.get_current_user)
    body: Dict[str, Any] = await request.json()
    enabled = bool(body.get("enabled", False))
    schedule_cron = (body.get("schedule_cron") or "").strip()
    username = user.get("username") or ""
    conn = _db()
    try:
        row = conn.execute(
            "SELECT id FROM cloud_connectors WHERE id = ? AND owner_username = ?",
            (connector_id, username),
        ).fetchone()
        if not row:
            return JSONResponse(
                {"success": False, "error": "Connector not found"}, status_code=404
            )
        conn.execute(
            "UPDATE cloud_connectors SET sync_enabled = ?, sync_schedule = ? WHERE id = ?",
            (1 if enabled else 0, schedule_cron if enabled else None, connector_id),
        )
        if enabled:
            task_row = conn.execute(
                "SELECT id FROM scheduled_tasks WHERE task_type = 'cloud_sync' AND target_id = ?",
                (connector_id,),
            ).fetchone()
            if task_row:
                conn.execute(
                    "UPDATE scheduled_tasks SET schedule_cron = ?, enabled = 1 WHERE id = ?",
                    (schedule_cron, task_row["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO scheduled_tasks (task_type, target_id, schedule_cron, enabled, created_at)
                    VALUES (?, ?, ?, 1, ?)
                    """,
                    ("cloud_sync", connector_id, schedule_cron, db.utc_now_iso()),
                )
        else:
            conn.execute(
                "UPDATE scheduled_tasks SET enabled = 0 WHERE task_type = 'cloud_sync' AND target_id = ?",
                (connector_id,),
            )
        conn.commit()
    finally:
        conn.close()
    return JSONResponse({"success": True})
