"""Data tables API (Data Grid + share + grants).

Backed by Postgres when POSTGRES_DSN/DATABASE_URL is set. Otherwise returns 503.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response

from automation_hub.core import auth, pg
from automation_hub.core import sqlserver_tables as sst

data_router = APIRouter(prefix="/api/data", tags=["data"])


def _require_pg() -> None:
    if not pg.is_enabled():
        raise HTTPException(
            status_code=503,
            detail="Postgres is not configured (set POSTGRES_DSN or DATABASE_URL)",
        )


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_username(u: str) -> str:
    return (u or "").strip().lower()


def _load_column_rules(conn, table_id: str) -> Dict[str, Dict[str, Any]]:
    """Return {column_name: rule_json} for a table."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, rule_json
            FROM table_column_rules
            WHERE table_id = %s
            """,
            (table_id,),
        )
        rows = cur.fetchall() or []
    return {r[0]: (r[1] or {}) for r in rows}


def _validate_cell(value: Any, rule: Dict[str, Any], col_name: str) -> Optional[str]:
    """Validate single cell against rule. Return error string or None."""
    if rule.get("required") and (
        value is None or (isinstance(value, str) and value.strip() == "")
    ):
        return f"Column '{col_name}' is required"

    if value is None:
        return None

    vtype = rule.get("type") or ""
    try:
        if vtype == "number":
            num = float(value)
            if "min" in rule and num < float(rule["min"]):
                return f"Column '{col_name}' must be >= {rule['min']}"
            if "max" in rule and num > float(rule["max"]):
                return f"Column '{col_name}' must be <= {rule['max']}"
        elif vtype == "integer":
            num = int(value)
            if "min" in rule and num < int(rule["min"]):
                return f"Column '{col_name}' must be >= {rule['min']}"
            if "max" in rule and num > int(rule["max"]):
                return f"Column '{col_name}' must be <= {rule['max']}"
        elif vtype == "string":
            s = str(value)
            if "min_length" in rule and len(s) < int(rule["min_length"]):
                return f"Column '{col_name}' length must be >= {rule['min_length']}"
            if "max_length" in rule and len(s) > int(rule["max_length"]):
                return f"Column '{col_name}' length must be <= {rule['max_length']}"
            if rule.get("regex"):
                import re

                if not re.fullmatch(rule["regex"], s):
                    return f"Column '{col_name}' does not match pattern"
        # simple date/boolean checks could be added later
    except Exception:
        return f"Column '{col_name}' has invalid value"

    return None


def _validate_rows(
    columns: List[Dict[str, Any]],
    rows: List[Dict[str, Any]],
    rules: Dict[str, Dict[str, Any]],
) -> Tuple[bool, List[str]]:
    """Validate all rows. Returns (ok, errors)."""
    if not rules:
        return True, []
    errors: List[str] = []
    col_fields = [c.get("field") or c.get("title") for c in columns]
    for row_idx, row in enumerate(rows):
        for col in col_fields:
            if not col or col not in rules:
                continue
            rule = rules[col] or {}
            err = _validate_cell(row.get(col), rule, col)
            if err:
                errors.append(f"Row {row_idx + 1}: {err}")
                if len(errors) >= 20:
                    return False, errors
    return (len(errors) == 0), errors


def _table_permission_for_user(conn, table_id: str, username: str, role: str) -> str:
    """Return permission string: owner/edit/view/view_nocopy/none."""
    if role == "admin":
        return "owner"
    username = _normalize_username(username)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT owner_username FROM tables_meta WHERE table_id = %s",
            (table_id,),
        )
        row = cur.fetchone()
        if not row:
            return "none"
        owner = _normalize_username(row[0])
        if owner == username:
            return "owner"

        cur.execute(
            "SELECT permission FROM table_grants WHERE table_id = %s AND grantee_username = %s",
            (table_id, username),
        )
        gr = cur.fetchone()
        if not gr:
            return "none"
        return (gr[0] or "").strip().lower() or "view"


def _get_table_meta(conn, table_id: str) -> Optional[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_id, title, owner_username, storage_backend, promote_status, promoted_sqlserver_conn_id
            FROM tables_meta
            WHERE table_id = %s
            """,
            (table_id,),
        )
        r = cur.fetchone()
        if not r:
            return None
        return {
            "table_id": r[0],
            "title": r[1],
            "owner_username": r[2],
            "storage_backend": (r[3] or "postgres").strip().lower(),
            "promote_status": (r[4] or "draft").strip().lower(),
            "promoted_sqlserver_conn_id": r[5],
        }


@data_router.get("/tables")
async def list_tables(request: Request):
    """List tables user can access (owner + grants)."""
    _require_pg()
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )
    username = user.get("username") or ""
    role = (user.get("role") or "user").strip().lower()

    with pg.pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT m.table_id, m.title, m.owner_username, m.created_at, m.updated_at,
                       m.last_opened_at, m.storage_backend, m.promote_status,
                       CASE WHEN f.username IS NULL THEN 0 ELSE 1 END AS is_favorite
                FROM tables_meta m
                LEFT JOIN table_grants g ON g.table_id = m.table_id
                LEFT JOIN table_favorites f ON f.table_id = m.table_id AND f.username = %s
                WHERE m.owner_username = %s OR g.grantee_username = %s
                ORDER BY COALESCE(m.last_opened_at, m.updated_at) DESC
                """,
                (username, username, username),
            )
            rows = cur.fetchall() or []

    tables = []
    for r in rows:
        tables.append(
            {
                "id": r[0],
                "title": r[1],
                "owner_username": r[2],
                "created_at": r[3].isoformat() if r[3] else "",
                "updated_at": r[4].isoformat() if r[4] else "",
                "last_opened_at": r[5].isoformat() if r[5] else None,
                "storage_backend": r[6] or "postgres",
                "promote_status": r[7] or "draft",
                "is_favorite": bool(r[8]),
            }
        )
    return JSONResponse({"success": True, "tables": tables, "role": role})


@data_router.post("/tables")
async def create_table(request: Request):
    """Create a new empty table owned by the current user."""
    _require_pg()
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )
    body: Dict[str, Any] = await request.json()
    title = (body.get("title") or "New table").strip()[:200]
    table_id = (body.get("table_id") or "").strip()
    if not table_id:
        table_id = f"t_{secrets.token_hex(8)}"

    username = user.get("username") or ""
    with pg.pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tables_meta(table_id, title, owner_username, created_at, updated_at, promote_status)
                VALUES (%s, %s, %s, NOW(), NOW(), 'draft')
                ON CONFLICT (table_id) DO NOTHING
                """,
                (table_id, title, username),
            )
            # default content
            cur.execute(
                """
                INSERT INTO tables_data(table_id, content, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (table_id) DO NOTHING
                """,
                (table_id, json.dumps({"columns": [], "rows": []})),
            )
        conn.commit()
    return JSONResponse({"success": True, "table": {"id": table_id, "title": title}})


@data_router.get("/grid")
async def get_grid(request: Request, table: str = Query(...)):
    """Get grid for a table (read allowed)."""
    _require_pg()
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )
    username = user.get("username") or ""
    role = (user.get("role") or "user").strip().lower()

    with pg.pg_connect() as conn:
        meta = _get_table_meta(conn, table)
        if not meta:
            return JSONResponse(
                {"success": False, "error": "Table not found"}, status_code=404
            )

        perm = _table_permission_for_user(conn, table, username, role)
        if perm == "none":
            return JSONResponse(
                {"success": False, "error": "Access denied"}, status_code=403
            )

        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tables_meta SET last_opened_at = NOW() WHERE table_id = %s",
                (table,),
            )
            if meta["storage_backend"] == "sqlserver":
                # Read from SQL Server (promoted). Keep Postgres metadata for permissions.
                try:
                    content_json = sst.get_table_content_json(table)
                except Exception as e:
                    return JSONResponse(
                        {"success": False, "error": f"SQL Server read failed: {e}"},
                        status_code=503,
                    )
                row = (content_json,) if content_json is not None else None
            else:
                cur.execute(
                    "SELECT content FROM tables_data WHERE table_id = %s", (table,)
                )
                row = cur.fetchone()
        conn.commit()

    content = row[0] if row else {"columns": [], "rows": []}
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except Exception:
            content = {"columns": [], "rows": []}
    return JSONResponse(
        {
            "success": True,
            "table_id": table,
            "permission": perm,
            "columns": (content or {}).get("columns") or [],
            "rows": (content or {}).get("rows") or [],
        }
    )


@data_router.post("/grid")
async def save_grid(request: Request):
    """Save grid for a table (write allowed)."""
    _require_pg()
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )
    username = user.get("username") or ""
    role = (user.get("role") or "user").strip().lower()
    body: Dict[str, Any] = await request.json()
    # Frontend uses query param `table` for table_id
    table_id = (request.query_params.get("table") or body.get("table_id") or "").strip()
    columns = body.get("columns") or []
    rows = body.get("rows") or []
    title = (body.get("title") or "").strip()
    if not table_id:
        return JSONResponse(
            {"success": False, "error": "table_id required"}, status_code=400
        )

    content = {"columns": columns, "rows": rows}

    with pg.pg_connect() as conn:
        meta = _get_table_meta(conn, table_id)
        if not meta:
            return JSONResponse(
                {"success": False, "error": "Table not found"}, status_code=404
            )

        perm = _table_permission_for_user(conn, table_id, username, role)
        if perm not in ("owner", "edit"):
            return JSONResponse(
                {"success": False, "error": "Write access denied"}, status_code=403
            )

        # Column validation (only for Postgres-backed tables)
        rules: Dict[str, Dict[str, Any]] = {}
        if meta["storage_backend"] != "sqlserver":
            rules = _load_column_rules(conn, table_id)
            ok, errors = _validate_rows(columns, rows, rules)
            if not ok:
                return JSONResponse(
                    {
                        "success": False,
                        "error": "Validation failed",
                        "errors": errors,
                    },
                    status_code=400,
                )

        # versioning: store last content as version before overwrite
        with conn.cursor() as cur:
            if meta["storage_backend"] == "sqlserver":
                # Best-effort: version from SQL Server content (if available)
                try:
                    prev_json = sst.get_table_content_json(table_id)
                    prev_content = json.loads(prev_json) if prev_json else None
                except Exception:
                    prev_content = None
            else:
                cur.execute(
                    "SELECT content FROM tables_data WHERE table_id = %s", (table_id,)
                )
                prev = cur.fetchone()
                prev_content = prev[0] if prev else None
            cur.execute(
                "SELECT COALESCE(MAX(version_number), 0) FROM table_versions WHERE table_id = %s",
                (table_id,),
            )
            v = cur.fetchone()
            next_ver = int(v[0] or 0) + 1
            cur.execute(
                """
                INSERT INTO table_versions(table_id, version_number, content)
                VALUES (%s, %s, %s::jsonb)
                """,
                (
                    table_id,
                    next_ver,
                    json.dumps(prev_content or {"columns": [], "rows": []}),
                ),
            )
            if meta["storage_backend"] == "sqlserver":
                if not sst.is_enabled():
                    return JSONResponse(
                        {
                            "success": False,
                            "error": "SQL Server storage not configured",
                        },
                        status_code=503,
                    )
                try:
                    sst.init_schema()
                    sst.upsert_table(
                        table_id=table_id,
                        owner_username=meta["owner_username"],
                        title=title[:200] if title else meta["title"],
                        content_json=json.dumps(content, ensure_ascii=False),
                    )
                except Exception as e:
                    return JSONResponse(
                        {"success": False, "error": f"SQL Server write failed: {e}"},
                        status_code=503,
                    )
            else:
                cur.execute(
                    """
                    INSERT INTO tables_data(table_id, content, updated_at)
                    VALUES (%s, %s::jsonb, NOW())
                    ON CONFLICT (table_id) DO UPDATE SET content = EXCLUDED.content, updated_at = NOW()
                    """,
                    (table_id, json.dumps(content)),
                )
            if title:
                cur.execute(
                    "UPDATE tables_meta SET title = %s, updated_at = NOW() WHERE table_id = %s",
                    (title[:200], table_id),
                )
            else:
                cur.execute(
                    "UPDATE tables_meta SET updated_at = NOW() WHERE table_id = %s",
                    (table_id,),
                )
        conn.commit()

    return JSONResponse({"success": True})


@data_router.delete("/tables/{table_id}")
async def delete_table(table_id: str, request: Request):
    """Delete a table (owner/admin only)."""
    _require_pg()
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )
    username = user.get("username") or ""
    role = (user.get("role") or "user").strip().lower()

    with pg.pg_connect() as conn:
        perm = _table_permission_for_user(conn, table_id, username, role)
        if perm != "owner" and role != "admin":
            return JSONResponse(
                {"success": False, "error": "Only owner/admin can delete"},
                status_code=403,
            )
        with conn.cursor() as cur:
            cur.execute("DELETE FROM table_grants WHERE table_id = %s", (table_id,))
            cur.execute("DELETE FROM table_favorites WHERE table_id = %s", (table_id,))
            cur.execute("DELETE FROM share_tokens WHERE table_id = %s", (table_id,))
            cur.execute("DELETE FROM table_versions WHERE table_id = %s", (table_id,))
            cur.execute("DELETE FROM tables_data WHERE table_id = %s", (table_id,))
            cur.execute("DELETE FROM tables_meta WHERE table_id = %s", (table_id,))
        conn.commit()
    return JSONResponse({"success": True})


@data_router.post("/tables/{table_id}/favorite")
async def toggle_favorite(table_id: str, request: Request):
    _require_pg()
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )
    username = user.get("username") or ""
    body: Dict[str, Any] = await request.json()
    enabled = bool(body.get("enabled", True))

    with pg.pg_connect() as conn:
        with conn.cursor() as cur:
            if enabled:
                cur.execute(
                    """
                    INSERT INTO table_favorites(username, table_id, created_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (username, table_id) DO NOTHING
                    """,
                    (username, table_id),
                )
            else:
                cur.execute(
                    "DELETE FROM table_favorites WHERE username = %s AND table_id = %s",
                    (username, table_id),
                )
        conn.commit()
    return JSONResponse({"success": True})


@data_router.post("/tables/{table_id}/grants")
async def grant_table_access(table_id: str, request: Request):
    _require_pg()
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )
    username = user.get("username") or ""
    role = (user.get("role") or "user").strip().lower()
    body: Dict[str, Any] = await request.json()
    # Frontend sends { username: "...", permission: "edit|view|view_nocopy" }
    grantee = _normalize_username(
        body.get("grantee_username") or body.get("username") or ""
    )
    permission = (body.get("permission") or "view").strip().lower()
    if not grantee:
        return JSONResponse(
            {"success": False, "error": "grantee_username required"}, status_code=400
        )
    if permission not in ("view", "edit", "view_nocopy"):
        return JSONResponse(
            {"success": False, "error": "Invalid permission"}, status_code=400
        )

    with pg.pg_connect() as conn:
        perm = _table_permission_for_user(conn, table_id, username, role)
        if perm != "owner" and role != "admin":
            return JSONResponse(
                {"success": False, "error": "Only owner/admin can grant"},
                status_code=403,
            )
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO table_grants(table_id, grantee_username, permission, created_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (table_id, grantee_username) DO UPDATE SET permission = EXCLUDED.permission
                """,
                (table_id, grantee, permission),
            )
        conn.commit()
    return JSONResponse({"success": True})


@data_router.post("/tables/{table_id}/share")
async def create_share_link(table_id: str, request: Request):
    _require_pg()
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )
    username = user.get("username") or ""
    role = (user.get("role") or "user").strip().lower()

    body: Dict[str, Any] = await request.json()
    # Frontend sends { expiry: "7d|30d|never" } in current UI.
    expiry = (body.get("expiry") or "").strip().lower()

    if expiry == "never":
        ttl_hours = 24 * 365 * 10  # 10 years (effectively no expiry)
    elif expiry.endswith("d") and expiry[:-1].isdigit():
        ttl_hours = int(expiry[:-1]) * 24
    else:
        # Backward compatible: ttl_days (1/7/30). Support ttl_hours too.
        ttl_days = body.get("ttl_days")
        ttl_hours = body.get("ttl_hours")
        if ttl_days is not None:
            try:
                ttl_hours = int(ttl_days) * 24
            except Exception:
                ttl_hours = 24
        ttl_hours = int(ttl_hours or 24)

    # Cap at 30 days unless explicitly "never"
    if expiry != "never":
        ttl_hours = max(1, min(int(ttl_hours), 24 * 30))
    token = secrets.token_urlsafe(24)
    expires_at = _now_utc() + timedelta(hours=ttl_hours)

    with pg.pg_connect() as conn:
        perm = _table_permission_for_user(conn, table_id, username, role)
        if perm not in ("owner", "edit"):
            return JSONResponse(
                {"success": False, "error": "Only owner/edit can share"},
                status_code=403,
            )
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO share_tokens(token, table_id, expires_at, created_at)
                VALUES (%s, %s, %s, NOW())
                """,
                (token, table_id, expires_at),
            )
        conn.commit()
    share_url = f"/shared/{token}"
    api_rows_url = f"/api/data/tables/share/{token}/rows"
    api_url = f"/api/data/tables/share/{token}"
    return JSONResponse(
        {
            "success": True,
            "token": token,
            "share_url": share_url,
            "url": share_url,
            # Power BI-friendly endpoints
            "api_url": api_url,
            "pbi_url": api_rows_url,
        }
    )


@data_router.get("/tables/share/{token}/rows")
async def get_shared_table_rows(token: str):
    """
    Power BI friendly endpoint.
    Returns a JSON array of row objects (no auth) so Power BI Web connector can ingest it.
    """
    _require_pg()
    with pg.pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_id, expires_at FROM share_tokens WHERE token = %s",
                (token,),
            )
            row = cur.fetchone()
            if not row:
                return JSONResponse(
                    {"success": False, "error": "Invalid share token"}, status_code=404
                )
            table_id = row[0]
            expires_at = row[1]
            if expires_at and expires_at < _now_utc():
                return JSONResponse(
                    {"success": False, "error": "Share token expired"}, status_code=410
                )

            cur.execute(
                "SELECT content FROM tables_data WHERE table_id = %s", (table_id,)
            )
            r2 = cur.fetchone()
            content = r2[0] if r2 else {"columns": [], "rows": []}

    if isinstance(content, str):
        try:
            content = json.loads(content)
        except Exception:
            content = {"columns": [], "rows": []}

    rows = (content or {}).get("rows") or []
    # Return raw list for Power BI convenience
    return JSONResponse(rows)


@data_router.post("/tables/{table_id}/submit-review")
async def submit_table_for_review(table_id: str, request: Request):
    """Owner can submit a table for admin review/promotion."""
    _require_pg()
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )
    username = user.get("username") or ""
    role = (user.get("role") or "user").strip().lower()

    with pg.pg_connect() as conn:
        perm = _table_permission_for_user(conn, table_id, username, role)
        if perm not in ("owner", "edit"):
            return JSONResponse(
                {"success": False, "error": "Only owner/editor can submit"},
                status_code=403,
            )
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tables_meta SET promote_status = 'pending_review', updated_at = NOW() WHERE table_id = %s",
                (table_id,),
            )
        conn.commit()
    return JSONResponse({"success": True})


@data_router.get("/tables/share/{token}")
async def get_shared_table(token: str):
    """Public read-only view (no auth)."""
    _require_pg()
    with pg.pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_id, expires_at FROM share_tokens WHERE token = %s",
                (token,),
            )
            row = cur.fetchone()
            if not row:
                return JSONResponse(
                    {"success": False, "error": "Invalid share token"}, status_code=404
                )
            table_id = row[0]
            expires_at = row[1]
            if expires_at and expires_at < _now_utc():
                return JSONResponse(
                    {"success": False, "error": "Share token expired"}, status_code=410
                )

            cur.execute(
                "SELECT content FROM tables_data WHERE table_id = %s", (table_id,)
            )
            r2 = cur.fetchone()
            content = r2[0] if r2 else {"columns": [], "rows": []}

    if isinstance(content, str):
        try:
            content = json.loads(content)
        except Exception:
            content = {"columns": [], "rows": []}
    return JSONResponse(
        {
            "success": True,
            "table_id": table_id,
            "columns": (content or {}).get("columns") or [],
            "rows": (content or {}).get("rows") or [],
        }
    )


@data_router.get("/tables/{table_id}/versions")
async def list_versions(table_id: str, request: Request):
    _require_pg()
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )
    username = user.get("username") or ""
    role = (user.get("role") or "user").strip().lower()

    with pg.pg_connect() as conn:
        perm = _table_permission_for_user(conn, table_id, username, role)
        if perm == "none":
            return JSONResponse(
                {"success": False, "error": "Access denied"}, status_code=403
            )
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, version_number, created_at
                FROM table_versions
                WHERE table_id = %s
                ORDER BY version_number DESC
                LIMIT 50
                """,
                (table_id,),
            )
            rows = cur.fetchall() or []
    versions = [
        {
            "id": r[0],
            "version_number": r[1],
            "created_at": r[2].isoformat() if r[2] else "",
        }
        for r in rows
    ]
    return JSONResponse({"success": True, "versions": versions})


@data_router.post("/tables/{table_id}/restore")
async def restore_version(table_id: str, request: Request):
    _require_pg()
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )
    username = user.get("username") or ""
    role = (user.get("role") or "user").strip().lower()
    body: Dict[str, Any] = await request.json()
    version_id = body.get("version_id")
    if not version_id:
        return JSONResponse(
            {"success": False, "error": "version_id required"}, status_code=400
        )

    with pg.pg_connect() as conn:
        perm = _table_permission_for_user(conn, table_id, username, role)
        if perm not in ("owner", "edit"):
            return JSONResponse(
                {"success": False, "error": "Write access denied"}, status_code=403
            )
        with conn.cursor() as cur:
            cur.execute(
                "SELECT content FROM table_versions WHERE id = %s AND table_id = %s",
                (version_id, table_id),
            )
            row = cur.fetchone()
            if not row:
                return JSONResponse(
                    {"success": False, "error": "Version not found"}, status_code=404
                )
            content = row[0] or {"columns": [], "rows": []}
            cur.execute(
                """
                INSERT INTO tables_data(table_id, content, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (table_id) DO UPDATE SET content = EXCLUDED.content, updated_at = NOW()
                """,
                (table_id, json.dumps(content)),
            )
            cur.execute(
                "UPDATE tables_meta SET updated_at = NOW() WHERE table_id = %s",
                (table_id,),
            )
        conn.commit()
    return JSONResponse({"success": True})


@data_router.get("/tables/{table_id}/export-json")
async def export_json(table_id: str, request: Request):
    _require_pg()
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )
    username = user.get("username") or ""
    role = (user.get("role") or "user").strip().lower()

    with pg.pg_connect() as conn:
        perm = _table_permission_for_user(conn, table_id, username, role)
        if perm == "none":
            return JSONResponse(
                {"success": False, "error": "Access denied"}, status_code=403
            )
        with conn.cursor() as cur:
            cur.execute(
                "SELECT content FROM tables_data WHERE table_id = %s", (table_id,)
            )
            row = cur.fetchone()
    content = row[0] if row else {"columns": [], "rows": []}
    payload = json.dumps(content, ensure_ascii=False).encode("utf-8")
    return Response(
        content=payload,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{table_id}.json"'},
    )


@data_router.post("/tables/{table_id}/import-json")
async def import_json(table_id: str, request: Request):
    _require_pg()
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )
    username = user.get("username") or ""
    role = (user.get("role") or "user").strip().lower()
    body: Dict[str, Any] = await request.json()
    columns = body.get("columns") or []
    rows = body.get("rows") or []
    content = {"columns": columns, "rows": rows}

    with pg.pg_connect() as conn:
        meta = _get_table_meta(conn, table_id)
        if not meta:
            return JSONResponse(
                {"success": False, "error": "Table not found"}, status_code=404
            )

        perm = _table_permission_for_user(conn, table_id, username, role)
        if perm not in ("owner", "edit"):
            return JSONResponse(
                {"success": False, "error": "Write access denied"}, status_code=403
            )
        with conn.cursor() as cur:
            # Column validation for imports (only for Postgres-backed tables)
            if meta["storage_backend"] != "sqlserver":
                rules = _load_column_rules(conn, table_id)
                ok, errors = _validate_rows(columns, rows, rules)
                if not ok:
                    return JSONResponse(
                        {
                            "success": False,
                            "error": "Validation failed",
                            "errors": errors,
                        },
                        status_code=400,
                    )
            if meta["storage_backend"] == "sqlserver":
                if not sst.is_enabled():
                    return JSONResponse(
                        {
                            "success": False,
                            "error": "SQL Server storage not configured",
                        },
                        status_code=503,
                    )
                try:
                    sst.init_schema()
                    sst.upsert_table(
                        table_id=table_id,
                        owner_username=meta["owner_username"],
                        title=meta["title"],
                        content_json=json.dumps(content, ensure_ascii=False),
                    )
                except Exception as e:
                    return JSONResponse(
                        {"success": False, "error": f"SQL Server write failed: {e}"},
                        status_code=503,
                    )
            else:
                cur.execute(
                    """
                    INSERT INTO tables_data(table_id, content, updated_at)
                    VALUES (%s, %s::jsonb, NOW())
                    ON CONFLICT (table_id) DO UPDATE SET content = EXCLUDED.content, updated_at = NOW()
                    """,
                    (table_id, json.dumps(content)),
                )
            cur.execute(
                "UPDATE tables_meta SET updated_at = NOW() WHERE table_id = %s",
                (table_id,),
            )
        conn.commit()
    return JSONResponse({"success": True})


@data_router.get("/tables/{table_id}/export-excel")
async def export_excel(table_id: str, request: Request):
    """Basic Excel export (requires pandas/openpyxl in requirements)."""
    _require_pg()
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )
    username = user.get("username") or ""
    role = (user.get("role") or "user").strip().lower()

    with pg.pg_connect() as conn:
        perm = _table_permission_for_user(conn, table_id, username, role)
        if perm == "none":
            return JSONResponse(
                {"success": False, "error": "Access denied"}, status_code=403
            )
        with conn.cursor() as cur:
            cur.execute(
                "SELECT content FROM tables_data WHERE table_id = %s", (table_id,)
            )
            row = cur.fetchone()
    content = row[0] if row else {"columns": [], "rows": []}
    try:
        import io
        import pandas as pd
    except Exception:
        return JSONResponse(
            {"success": False, "error": "pandas/openpyxl not available"},
            status_code=503,
        )
    cols = [
        c.get("title") or c.get("field") for c in (content or {}).get("columns") or []
    ]
    data_rows = (content or {}).get("rows") or []
    df = pd.DataFrame(data_rows)
    # Ensure column order if possible
    if cols:
        try:
            df = df[cols]
        except Exception:
            pass
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Table")
    out.seek(0)
    return Response(
        content=out.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{table_id}.xlsx"'},
    )
