from __future__ import annotations

import json
import re
import secrets
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from automation_hub.core import auth, db

MODULE_KEY = "process_designer"
ADMIN_MODULE_KEY = "process_designer_admin"
FIELD_TYPES = {
    "single_line",
    "multi_line",
    "number",
    "date",
    "single_select",
    "multi_select",
    "user_picker",
    "checkbox",
    "html",
}

router = APIRouter(prefix="/api/processes", tags=["process-designer"])
page_router = APIRouter(tags=["process-designer"])


def _user(request: Request) -> Dict[str, Any]:
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def _can_manage(user: Dict[str, Any]) -> bool:
    return user.get("role") == "admin" or ADMIN_MODULE_KEY in (
        user.get("modules") or []
    )


def _can_use(user: Dict[str, Any]) -> bool:
    modules = user.get("modules") or []
    return _can_manage(user) or MODULE_KEY in modules


def _slug(value: Any, fallback: str) -> str:
    result = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or "")).strip("_")
    return (result or fallback)[:80]


def _json(value: str, fallback):
    try:
        parsed = json.loads(value or "")
        return parsed
    except (TypeError, ValueError):
        return fallback


def _scope_visible(row: Dict[str, Any], user: Dict[str, Any], module: str) -> bool:
    if _can_manage(user):
        return True
    modules = _json(row.get("scope_modules_json"), [])
    if row.get("scope_type") == "global":
        return True
    return bool(module and module in modules and module in (user.get("modules") or []))


def _field_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "key": row["field_key"],
        "label": row["label"],
        "type": row["field_type"],
        "config": _json(row["config_json"], {}),
        "scope_type": row["scope_type"],
        "scope_modules": _json(row["scope_modules_json"], []),
        "visibility": _json(row["visibility_json"], {}),
        "created_by": row["created_by"],
        "is_active": bool(row["is_active"]),
    }


def _workflow_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "key": row["workflow_key"],
        "name": row["name"],
        "description": row["description"] or "",
        "scope_type": row["scope_type"],
        "scope_modules": _json(row["scope_modules_json"], []),
        "statuses": _json(row["statuses_json"], []),
        "transitions": _json(row["transitions_json"], []),
        "manage_policy": _json(row["manage_policy_json"], {}),
        "created_by": row["created_by"],
        "is_active": bool(row["is_active"]),
    }


@page_router.get("/process-designer", response_class=HTMLResponse)
async def process_designer_page(request: Request):
    user = auth.get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not _can_manage(user):
        return RedirectResponse("/summary", status_code=302)
    from app import templates

    return templates.TemplateResponse(
        request=request,
        name="processes/index.html",
        context={"request": request, "user": user},
    )


@router.get("/meta")
async def meta(request: Request):
    user = _user(request)
    if not _can_use(user):
        raise HTTPException(status_code=403, detail="Process Designer access required")
    from automation_hub.core.constants import MODULES

    return JSONResponse(
        {
            "success": True,
            "can_manage": _can_manage(user),
            "field_types": sorted(FIELD_TYPES),
            "modules": MODULES,
        }
    )


@router.get("/fields")
async def list_fields(request: Request, module: str = ""):
    user = _user(request)
    if not _can_use(user) and not module:
        raise HTTPException(status_code=403, detail="Access denied")
    conn = db.db_connect()
    try:
        rows = conn.execute(
            "SELECT * FROM custom_field_definitions WHERE is_active = 1 ORDER BY label"
        ).fetchall()
        fields = [_field_dict(row) for row in rows if _scope_visible(row, user, module)]
        return JSONResponse({"success": True, "fields": fields})
    finally:
        conn.close()


@router.post("/fields")
async def save_field(request: Request):
    user = _user(request)
    if not _can_manage(user):
        raise HTTPException(status_code=403, detail="Process admin access required")
    payload = await request.json()
    field_type = str(payload.get("type") or "single_line")
    if field_type not in FIELD_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported field type")
    field_id = str(payload.get("id") or f"field_{secrets.token_hex(6)}")
    key = _slug(payload.get("key") or payload.get("label"), field_id)
    scope_type = "modules" if payload.get("scope_type") == "modules" else "global"
    now = db.utc_now_iso()
    conn = db.db_connect()
    try:
        conn.execute(
            """
            INSERT INTO custom_field_definitions (
                id, field_key, label, field_type, config_json, scope_type,
                scope_modules_json, visibility_json, created_by, created_at,
                updated_at, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(id) DO UPDATE SET field_key=excluded.field_key,
                label=excluded.label, field_type=excluded.field_type,
                config_json=excluded.config_json, scope_type=excluded.scope_type,
                scope_modules_json=excluded.scope_modules_json,
                visibility_json=excluded.visibility_json, updated_at=excluded.updated_at
            """,
            (
                field_id,
                key,
                str(payload.get("label") or key)[:160],
                field_type,
                json.dumps(payload.get("config") or {}),
                scope_type,
                json.dumps(payload.get("scope_modules") or []),
                json.dumps(payload.get("visibility") or {}),
                user.get("username"),
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM custom_field_definitions WHERE id = ?", (field_id,)
        ).fetchone()
        return JSONResponse({"success": True, "field": _field_dict(row)})
    finally:
        conn.close()


@router.get("/workflows")
async def list_workflows(request: Request, module: str = ""):
    user = _user(request)
    conn = db.db_connect()
    try:
        rows = conn.execute(
            "SELECT * FROM workflow_definitions WHERE is_active = 1 ORDER BY name"
        ).fetchall()
        items = [
            _workflow_dict(row) for row in rows if _scope_visible(row, user, module)
        ]
        return JSONResponse({"success": True, "workflows": items})
    finally:
        conn.close()


@router.post("/workflows")
async def save_workflow(request: Request):
    user = _user(request)
    if not _can_manage(user):
        raise HTTPException(status_code=403, detail="Process admin access required")
    payload = await request.json()
    workflow_id = str(payload.get("id") or f"workflow_{secrets.token_hex(6)}")
    key = _slug(payload.get("key") or payload.get("name"), workflow_id)
    now = db.utc_now_iso()
    conn = db.db_connect()
    try:
        conn.execute(
            """
            INSERT INTO workflow_definitions (
                id, workflow_key, name, description, scope_type,
                scope_modules_json, statuses_json, transitions_json,
                manage_policy_json, created_by, created_at, updated_at, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(id) DO UPDATE SET workflow_key=excluded.workflow_key,
                name=excluded.name, description=excluded.description,
                scope_type=excluded.scope_type,
                scope_modules_json=excluded.scope_modules_json,
                statuses_json=excluded.statuses_json,
                transitions_json=excluded.transitions_json,
                manage_policy_json=excluded.manage_policy_json,
                updated_at=excluded.updated_at
            """,
            (
                workflow_id,
                key,
                str(payload.get("name") or key)[:160],
                str(payload.get("description") or "")[:1000],
                "modules" if payload.get("scope_type") == "modules" else "global",
                json.dumps(payload.get("scope_modules") or []),
                json.dumps(payload.get("statuses") or []),
                json.dumps(payload.get("transitions") or []),
                json.dumps(payload.get("manage_policy") or {}),
                user.get("username"),
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM workflow_definitions WHERE id = ?", (workflow_id,)
        ).fetchone()
        return JSONResponse({"success": True, "workflow": _workflow_dict(row)})
    finally:
        conn.close()
