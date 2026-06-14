"""Ticketing and project workflow module.

Module permissions:
- feedback_180: legacy project portal access.
- feedback_180_admin: project workflow administration.
"""

from __future__ import annotations

import json
import os
import secrets
import re
import csv
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
import bleach

from automation_hub.core import auth, db
from automation_hub.services import enterprise_auth
from automation_hub.services import employee_roster

MODULE_KEY = "feedback_180"
ADMIN_MODULE_KEY = "feedback_180_admin"

router = APIRouter(prefix="/api/ticketing", tags=["ticketing"])
feedback_handlers = APIRouter()

FIELD_TYPES = {
    "single_line",
    "multi_line",
    "number",
    "date",
    "single_select",
    "multi_select",
    "user_picker",
    "single_user_picker",
    "multi_user_picker",
    "checkbox",
}
HTML_TAGS = [
    "p",
    "br",
    "strong",
    "em",
    "u",
    "h1",
    "h2",
    "h3",
    "ul",
    "ol",
    "li",
    "blockquote",
    "a",
    "code",
    "pre",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
]
HTML_ATTRIBUTES = {"a": ["href", "title", "target"], "*": ["class"]}


def _store_path() -> Path:
    data_dir = Path(os.getenv("APP_DATA_DIR", ".")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "feedback_180_projects.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_store() -> Dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return {"projects": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"projects": []}
    if not isinstance(data, dict) or not isinstance(data.get("projects"), list):
        return {"projects": []}
    return data


def _save_store(data: Dict[str, Any]) -> None:
    path = _store_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _current_user(request: Request) -> Dict[str, Any]:
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def _is_feedback_admin(user: Dict[str, Any]) -> bool:
    return user.get("role") == "admin" or ADMIN_MODULE_KEY in (
        user.get("modules") or []
    )


def _has_feedback_access(user: Dict[str, Any]) -> bool:
    modules = user.get("modules") or []
    return (
        user.get("role") == "admin"
        or MODULE_KEY in modules
        or ADMIN_MODULE_KEY in modules
    )


def _require_feedback_access(request: Request) -> Dict[str, Any]:
    user = _current_user(request)
    if not _has_feedback_access(user):
        raise HTTPException(status_code=403, detail="180 Feedback access required")
    return user


def _require_feedback_admin(request: Request) -> Dict[str, Any]:
    user = _require_feedback_access(request)
    if not _is_feedback_admin(user):
        raise HTTPException(
            status_code=403, detail="180 Feedback admin access required"
        )
    return user


def _default_workflow() -> Dict[str, Any]:
    return {
        "scale_min": 1,
        "scale_max": 5,
        "anonymous": False,
        "deadline_days": 0,
        "statuses": [],
        "screens": [],
        "transitions": [],
    }


def _safe_html(value: Any) -> str:
    return bleach.clean(
        str(value or "")[:50000],
        tags=HTML_TAGS,
        attributes=HTML_ATTRIBUTES,
        protocols=["http", "https", "mailto"],
        strip=True,
    )


def _slug(value: Any, fallback: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or "").strip()).strip("_")
    return (clean or fallback)[:80]


def _clean_form_field(field: Dict[str, Any], index: int) -> Dict[str, Any]:
    field_type = str(field.get("type") or "single_line")
    if field_type not in FIELD_TYPES:
        field_type = "single_line"
    source = str(field.get("user_source") or "database")
    if source not in {"database", "ldap"}:
        source = "database"
    return {
        "id": str(field.get("id") or f"field_{secrets.token_hex(4)}")[:80],
        "key": _slug(field.get("key") or field.get("label"), f"field_{index + 1}"),
        "label": str(field.get("label") or "")[:160],
        "type": field_type,
        "required": bool(field.get("required")),
        "placeholder": str(field.get("placeholder") or "")[:300],
        "help_text": str(field.get("help_text") or "")[:500],
        "options": [
            str(option)[:160]
            for option in (field.get("options") or [])
            if str(option).strip()
        ][:200],
        "user_source": source,
        "condition_field": str(field.get("condition_field") or "")[:80],
        "condition_operator": str(field.get("condition_operator") or "equals")[:30],
        "condition_value": str(field.get("condition_value") or "")[:300],
    }


def _clean_transition(item: Dict[str, Any], index: int) -> Dict[str, Any]:
    approver_type = str(item.get("approver_type") or "any_user")
    if approver_type not in {"any_user", "manager", "user", "role", "feedback_admin"}:
        approver_type = "any_user"
    return {
        "id": str(item.get("id") or f"transition_{secrets.token_hex(4)}")[:80],
        "name": str(item.get("name") or "")[:120],
        "from_status": str(item.get("from_status") or "")[:80],
        "to_status": str(item.get("to_status") or "")[:80],
        "approver_type": approver_type,
        "approver_value": str(item.get("approver_value") or "")[:160],
        "condition_field": str(item.get("condition_field") or "")[:80],
        "condition_operator": str(item.get("condition_operator") or "equals")[:30],
        "condition_value": str(item.get("condition_value") or "")[:300],
    }


def _clean_status(status: Dict[str, Any], index: int) -> Dict[str, Any]:
    return {
        "id": str(status.get("id") or f"status_{secrets.token_hex(4)}")[:80],
        "name": str(status.get("name") or "")[:100],
        "category": str(status.get("category") or "todo")[:40],
        "screen_id": str(status.get("screen_id") or "")[:80],
        "description": str(status.get("description") or "")[:500],
        "order": index,
        "x": int(status.get("x") or 0),
        "y": int(status.get("y") or 0),
    }


def _sanitize_project(
    project: Dict[str, Any],
    user: Dict[str, Any],
    existing: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    now = _now()
    clean = dict(project or {})
    clean["id"] = str(clean.get("id") or f"fb_{secrets.token_hex(6)}")
    clean["title"] = str(clean.get("title") or "Untitled form")[:160]
    clean["description"] = str(clean.get("description") or "")[:1000]
    clean["cycle"] = str(clean.get("cycle") or "")[:80]
    clean["status"] = str(clean.get("status") or "")[:80]
    clean["category"] = str(clean.get("category") or "Common Requests")[:120]
    clean["icon"] = str(clean.get("icon") or "❓")[:80]
    key_val = clean.get("key") or clean.get("title") or "PROJ"
    clean["key"] = _slug(key_val, "PROJ").upper()[:10]
    clean["owner_username"] = (
        (existing or {}).get("owner_username") or user.get("username") or ""
    )
    clean["created_at"] = (
        (existing or {}).get("created_at") or clean.get("created_at") or now
    )
    clean["hidden"] = bool(project.get("hidden", (existing or {}).get("hidden", False)))
    clean["allowed_users"] = [
        str(u).strip()
        for u in project.get("allowed_users", (existing or {}).get("allowed_users", []))
        if str(u).strip()
    ]
    clean["allowed_groups"] = [
        str(g).strip()
        for g in project.get(
            "allowed_groups", (existing or {}).get("allowed_groups", [])
        )
        if str(g).strip()
    ]
    clean["updated_at"] = now

    workflow = clean.get("workflow") if isinstance(clean.get("workflow"), dict) else {}
    statuses = (
        workflow.get("statuses") if isinstance(workflow.get("statuses"), list) else []
    )
    screens = (
        workflow.get("screens") if isinstance(workflow.get("screens"), list) else []
    )
    clean["workflow"] = {
        "scale_min": int(workflow.get("scale_min") or 1),
        "scale_max": int(workflow.get("scale_max") or 5),
        "anonymous": bool(workflow.get("anonymous", True)),
        "deadline_days": int(workflow.get("deadline_days") or 0),
        "statuses": [
            _clean_status(status, idx)
            for idx, status in enumerate(statuses[:20])
            if isinstance(status, dict)
        ],
        "screens": [
            {
                "id": str(screen.get("id") or f"screen_{idx + 1}")[:80],
                "name": str(screen.get("name") or "")[:100],
                "description": str(screen.get("description") or "")[:500],
                "fields": [
                    str(field)[:80]
                    for field in (screen.get("fields") or [])
                    if str(field).strip()
                ][:40],
            }
            for idx, screen in enumerate(screens[:20])
            if isinstance(screen, dict)
        ],
        "transitions": [
            _clean_transition(item, idx)
            for idx, item in enumerate(workflow.get("transitions") or [])
            if isinstance(item, dict)
        ][:50],
    }

    participants = (
        clean.get("participants") if isinstance(clean.get("participants"), dict) else {}
    )
    clean["participants"] = {
        "subjects": [
            str(v)[:160] for v in participants.get("subjects", []) if str(v).strip()
        ][:300],
        "reviewers": [
            str(v)[:160] for v in participants.get("reviewers", []) if str(v).strip()
        ][:1000],
        "matrix": (
            participants.get("matrix", {})
            if isinstance(participants.get("matrix"), dict)
            else {}
        ),
    }

    questions = (
        clean.get("questions") if isinstance(clean.get("questions"), list) else []
    )
    clean["questions"] = [
        {
            "id": str(q.get("id") or f"q_{idx + 1}"),
            "text": str(q.get("text") or "")[:500],
            "category": str(q.get("category") or "")[:80],
            "type": str(q.get("type") or "text")[:40],
            "required": bool(q.get("required", False)),
        }
        for idx, q in enumerate(questions[:80])
        if isinstance(q, dict) and str(q.get("text") or "").strip()
    ]
    form_fields = (
        clean.get("form_fields") if isinstance(clean.get("form_fields"), list) else []
    )
    clean["form_fields"] = [
        _clean_form_field(field, idx)
        for idx, field in enumerate(form_fields[:100])
        if isinstance(field, dict)
    ]
    tickets = clean.get("tickets") if isinstance(clean.get("tickets"), list) else []
    clean["tickets"] = [
        ticket for ticket in tickets[:10000] if isinstance(ticket, dict)
    ]
    responses = (
        clean.get("responses") if isinstance(clean.get("responses"), list) else []
    )
    clean["responses"] = [r for r in responses[:5000] if isinstance(r, dict)]
    return clean


def _project_visible(project: Dict[str, Any], user: Dict[str, Any]) -> bool:
    if _is_feedback_admin(user):
        return True
    if project.get("hidden"):
        return False
    username = (user.get("username") or "").strip().lower()
    role = (user.get("role") or "").strip().lower()
    user_modules = [m.strip().lower() for m in user.get("modules") or []]

    allowed_users = [u.strip().lower() for u in project.get("allowed_users") or []]
    allowed_groups = [g.strip().lower() for g in project.get("allowed_groups") or []]
    if allowed_users or allowed_groups:
        user_match = username in allowed_users
        group_match = role in allowed_groups or any(
            m in allowed_groups for m in user_modules
        )
        if not (user_match or group_match):
            return False

    participants = project.get("participants") or {}
    manages_ticket = any(
        (ticket.get("manager_username") or "").strip().lower() == username
        for ticket in project.get("tickets", [])
    )
    return (
        username in [s.strip().lower() for s in participants.get("subjects") or []]
        or username in [r.strip().lower() for r in participants.get("reviewers") or []]
        or (project.get("owner_username") or "").strip().lower() == username
        or manages_ticket
    )


def _visible_project(project: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    visible = dict(project)
    if not _is_feedback_admin(user):
        visible["tickets"] = [
            ticket
            for ticket in project.get("tickets", [])
            if _ticket_visible(project, ticket, user)
        ]
    return visible


def _find_project(store: Dict[str, Any], project_id: str) -> Optional[Dict[str, Any]]:
    return next(
        (item for item in store.get("projects", []) if item.get("id") == project_id),
        None,
    )


def _ticket_visible(
    project: Dict[str, Any], ticket: Dict[str, Any], user: Dict[str, Any]
) -> bool:
    if _is_feedback_admin(user):
        return True
    if ticket.get("hidden"):
        return False
    username = (user.get("username") or "").strip().lower()
    role = (user.get("role") or "").strip().lower()
    user_modules = [m.strip().lower() for m in user.get("modules") or []]

    allowed_users = [u.strip().lower() for u in ticket.get("allowed_users") or []]
    allowed_groups = [g.strip().lower() for g in ticket.get("allowed_groups") or []]
    if allowed_users or allowed_groups:
        user_match = username in allowed_users
        group_match = role in allowed_groups or any(
            m in allowed_groups for m in user_modules
        )
        if not (user_match or group_match):
            return False

    return username in {
        (ticket.get("created_by") or "").strip().lower(),
        (ticket.get("assigned_to") or "").strip().lower(),
        (ticket.get("manager_username") or "").strip().lower(),
    } or _project_visible(project, user)


def _condition_matches(rule: Dict[str, Any], values: Dict[str, Any]) -> bool:
    key = rule.get("condition_field")
    if not key:
        return True
    actual = values.get(key)
    expected = rule.get("condition_value")
    operator = rule.get("condition_operator") or "equals"
    if operator == "not_equals":
        return str(actual) != str(expected)
    if operator == "contains":
        return str(expected).lower() in str(actual).lower()
    if operator == "is_set":
        return actual not in (None, "", [])
    return str(actual) == str(expected)


def _can_transition(
    transition: Dict[str, Any], ticket: Dict[str, Any], user: Dict[str, Any]
) -> bool:
    username = user.get("username") or ""
    kind = transition.get("approver_type")
    if _is_feedback_admin(user) or kind == "any_user":
        return True
    if kind == "manager":
        return username == ticket.get("manager_username")
    if kind == "user":
        return username == transition.get("approver_value")
    if kind == "role":
        return user.get("role") == transition.get("approver_value")
    return False


def _local_users(query: str) -> List[Dict[str, str]]:
    conn = db.db_connect(db.get_db_file())
    try:
        pattern = f"%{query.strip()}%"
        rows = conn.execute(
            """
            SELECT username, first_name, last_name, email, auth_provider
            FROM users
            WHERE status = 'active' AND (
                username LIKE ? OR first_name LIKE ? OR last_name LIKE ? OR email LIKE ?
            )
            ORDER BY username LIMIT 50
            """,
            (pattern, pattern, pattern, pattern),
        ).fetchall()
        return [
            {
                "id": row["username"],
                "username": row["username"],
                "label": (
                    f"{row['first_name'] or ''} {row['last_name'] or ''}".strip()
                    or row["username"]
                ),
                "email": row["email"] or row["username"],
                "source": row["auth_provider"] or "database",
            }
            for row in rows
        ]
    finally:
        conn.close()


@router.get("/meta")
async def feedback_meta(request: Request):
    user = _require_feedback_access(request)
    return JSONResponse(
        {
            "success": True,
            "module": MODULE_KEY,
            "admin_module": ADMIN_MODULE_KEY,
            "permissions": {
                "can_manage_workflow": _is_feedback_admin(user),
                "can_respond": True,
            },
            "field_types": sorted(FIELD_TYPES),
        }
    )


@router.get("/users")
async def feedback_users(request: Request, source: str = "database", query: str = ""):
    _require_feedback_access(request)
    if source == "ldap":
        users = enterprise_auth.search_ldap_users(query)
    else:
        users = _local_users(query)
    return JSONResponse({"success": True, "users": users, "source": source})


@router.get("/projects")
async def list_feedback_projects(request: Request):
    user = _require_feedback_access(request)
    store = _load_store()
    projects = [
        _visible_project(p, user)
        for p in store.get("projects", [])
        if _project_visible(p, user)
    ]
    projects.sort(key=lambda p: p.get("updated_at") or "", reverse=True)
    return JSONResponse(
        {
            "success": True,
            "projects": projects,
            "permissions": {"can_manage_workflow": _is_feedback_admin(user)},
        }
    )


@router.post("/projects")
async def save_feedback_project(request: Request):
    user = _require_feedback_admin(request)
    payload = await request.json()
    incoming = payload.get("project") if isinstance(payload, dict) else None
    if not isinstance(incoming, dict):
        return JSONResponse(
            {"success": False, "error": "Project payload is required"}, status_code=400
        )

    store = _load_store()
    projects: List[Dict[str, Any]] = store.setdefault("projects", [])
    existing_idx = next(
        (
            idx
            for idx, item in enumerate(projects)
            if item.get("id") == incoming.get("id")
        ),
        None,
    )
    existing = projects[existing_idx] if existing_idx is not None else None
    project = _sanitize_project(incoming, user, existing)
    if existing_idx is None:
        projects.append(project)
    else:
        projects[existing_idx] = project
    _save_store(store)
    return JSONResponse({"success": True, "project": project})


@router.delete("/projects/{project_id}")
async def delete_feedback_project(project_id: str, request: Request):
    _require_feedback_admin(request)
    store = _load_store()
    projects = store.get("projects", [])
    if not any(p.get("id") == project_id for p in projects):
        return JSONResponse(
            {"success": False, "error": "Project not found"}, status_code=404
        )
    store["projects"] = [p for p in projects if p.get("id") != project_id]
    _save_store(store)
    return JSONResponse({"success": True})


@router.post("/projects/{project_id}/responses")
async def submit_feedback_response(project_id: str, request: Request):
    user = _require_feedback_access(request)
    payload = await request.json()
    response = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(response, dict):
        return JSONResponse(
            {"success": False, "error": "Response payload is required"}, status_code=400
        )
    store = _load_store()
    projects = store.get("projects", [])
    project = next((p for p in projects if p.get("id") == project_id), None)
    if not project:
        return JSONResponse(
            {"success": False, "error": "Project not found"}, status_code=404
        )
    if not _project_visible(project, user):
        return JSONResponse(
            {"success": False, "error": "Permission denied"}, status_code=403
        )
    responses = project.setdefault("responses", [])
    responses.append(
        {
            "id": f"resp_{secrets.token_hex(6)}",
            "submitted_by": user.get("username"),
            "submitted_at": _now(),
            "subject": str(response.get("subject") or "")[:160],
            "reviewer": str(response.get("reviewer") or user.get("username") or "")[
                :160
            ],
            "answers": (
                response.get("answers", {})
                if isinstance(response.get("answers"), dict)
                else {}
            ),
            "comment": str(response.get("comment") or "")[:2000],
        }
    )
    project["updated_at"] = _now()
    _save_store(store)
    return JSONResponse({"success": True, "responses_count": len(responses)})


@router.get("/tickets")
async def list_process_tickets(request: Request, scope: str = "mine"):
    user = _require_feedback_access(request)
    username = user.get("username") or ""
    tickets = []
    for project in _load_store().get("projects", []):
        for ticket in project.get("tickets", []):
            allowed = (
                _is_feedback_admin(user)
                if scope == "all"
                else (
                    ticket.get("manager_username") == username
                    if scope == "approvals"
                    else ticket.get("created_by") == username
                    or ticket.get("assigned_to") == username
                )
            )
            if allowed:
                tickets.append(
                    {
                        **ticket,
                        "project_id": project.get("id"),
                        "project_title": project.get("title"),
                    }
                )
    tickets.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return JSONResponse({"success": True, "tickets": tickets, "scope": scope})


@router.get("/tickets/report.csv")
async def process_ticket_report(request: Request, scope: str = "mine"):
    data = await list_process_tickets(request, scope)
    payload = json.loads(data.body)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "ticket_id",
            "project",
            "title",
            "status",
            "created_by",
            "assigned_to",
            "approver",
            "created_at",
            "updated_at",
        ]
    )
    for ticket in payload["tickets"]:
        writer.writerow(
            [
                ticket.get("id"),
                ticket.get("project_title"),
                ticket.get("title"),
                ticket.get("status"),
                ticket.get("created_by"),
                ticket.get("assigned_to"),
                ticket.get("manager_username"),
                ticket.get("created_at"),
                ticket.get("updated_at"),
            ]
        )
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="servexa-{scope}-tickets.csv"'
        },
    )


@router.post("/projects/{project_id}/tickets")
async def create_feedback_ticket(project_id: str, request: Request):
    user = _require_feedback_access(request)
    payload = await request.json()
    incoming = payload.get("ticket") if isinstance(payload, dict) else None
    if not isinstance(incoming, dict):
        raise HTTPException(status_code=400, detail="Ticket payload is required")
    store = _load_store()
    project = _find_project(store, project_id)
    if not project or not _project_visible(project, user):
        raise HTTPException(status_code=404, detail="Project not found")
    values = (
        incoming.get("field_values")
        if isinstance(incoming.get("field_values"), dict)
        else {}
    )
    for field in project.get("form_fields") or []:
        if field.get("required") and _condition_matches(field, values):
            if values.get(field.get("key")) in (None, "", []):
                raise HTTPException(
                    status_code=400, detail=f"{field.get('label')} is required"
                )
    statuses = project.get("workflow", {}).get("statuses") or []
    project_key = _slug(
        project.get("key") or project.get("title") or "PROJ", "PROJ"
    ).upper()[:10]
    tickets = project.setdefault("tickets", [])
    max_num = 100
    for t in tickets:
        tid = t.get("id", "")
        if "-" in tid:
            try:
                num = int(tid.split("-")[-1])
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    next_num = max_num + 1
    ticket_id = f"{project_key}-{next_num}"

    ticket = {
        "id": ticket_id,
        "title": str(incoming.get("title") or "Untitled ticket")[:200],
        "description": str(incoming.get("description") or "")[:10000],
        "description_html": _safe_html(incoming.get("description_html")),
        "created_by": user.get("username"),
        "assigned_to": str(incoming.get("assigned_to") or "")[:160],
        "manager_username": str(incoming.get("manager_username") or "")[:160],
        "status": str(
            incoming.get("status") or (statuses[0].get("id") if statuses else "")
        )[:80],
        "field_values": values,
        "comments": [],
        "history": [{"at": _now(), "by": user.get("username"), "action": "created"}],
        "created_at": _now(),
        "updated_at": _now(),
    }
    project.setdefault("tickets", []).append(ticket)
    project["updated_at"] = _now()
    _save_store(store)
    return JSONResponse({"success": True, "ticket": ticket})


@router.post("/projects/{project_id}/tickets/{ticket_id}/comments")
async def add_ticket_comment(project_id: str, ticket_id: str, request: Request):
    user = _require_feedback_access(request)
    payload = await request.json()
    store = _load_store()
    project = _find_project(store, project_id)
    ticket = next(
        (t for t in (project or {}).get("tickets", []) if t.get("id") == ticket_id),
        None,
    )
    if not project or not ticket or not _ticket_visible(project, ticket, user):
        raise HTTPException(status_code=404, detail="Ticket not found")
    comment = {
        "id": f"comment_{secrets.token_hex(5)}",
        "author": user.get("username"),
        "body": str(payload.get("body") or "")[:10000],
        "body_html": _safe_html(payload.get("body_html")),
        "created_at": _now(),
    }
    if not comment["body"] and not comment["body_html"]:
        raise HTTPException(status_code=400, detail="Comment cannot be empty")
    ticket.setdefault("comments", []).append(comment)
    ticket["updated_at"] = _now()
    _save_store(store)
    return JSONResponse({"success": True, "comment": comment})


@router.post("/projects/{project_id}/tickets/{ticket_id}/transition")
async def transition_ticket(project_id: str, ticket_id: str, request: Request):
    user = _require_feedback_access(request)
    payload = await request.json()
    store = _load_store()
    project = _find_project(store, project_id)
    ticket = next(
        (t for t in (project or {}).get("tickets", []) if t.get("id") == ticket_id),
        None,
    )
    if not project or not ticket or not _ticket_visible(project, ticket, user):
        raise HTTPException(status_code=404, detail="Ticket not found")
    transition = next(
        (
            item
            for item in project.get("workflow", {}).get("transitions", [])
            if item.get("id") == payload.get("transition_id")
            and item.get("from_status") == ticket.get("status")
        ),
        None,
    )
    if not transition:
        raise HTTPException(status_code=400, detail="Transition is not available")
    if not _condition_matches(transition, ticket.get("field_values") or {}):
        raise HTTPException(status_code=400, detail="Transition condition is not met")
    if not _can_transition(transition, ticket, user):
        raise HTTPException(
            status_code=403, detail="Approval is required from the configured approver"
        )
    previous = ticket.get("status")
    ticket["status"] = transition.get("to_status")
    ticket["updated_at"] = _now()
    ticket.setdefault("history", []).append(
        {
            "at": _now(),
            "by": user.get("username"),
            "action": "transition",
            "transition": transition.get("name"),
            "from": previous,
            "to": ticket.get("status"),
        }
    )
    _save_store(store)
    return JSONResponse({"success": True, "ticket": ticket})


@router.post("/projects/{project_id}/tickets/{ticket_id}/update")
async def update_feedback_ticket(project_id: str, ticket_id: str, request: Request):
    user = _require_feedback_access(request)
    payload = await request.json()
    incoming = payload.get("ticket")
    if not isinstance(incoming, dict):
        raise HTTPException(status_code=400, detail="Ticket payload is required")
    store = _load_store()
    project = _find_project(store, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    ticket = next(
        (t for t in project.get("tickets", []) if t.get("id") == ticket_id),
        None,
    )
    if not ticket or not _ticket_visible(project, ticket, user):
        raise HTTPException(status_code=404, detail="Ticket not found")
    username = user.get("username")
    can_edit = (
        user.get("role") == "admin"
        or ticket.get("created_by") == username
        or ticket.get("assigned_to") == username
        or ticket.get("manager_username") == username
    )
    if not can_edit:
        raise HTTPException(status_code=403, detail="Permission denied")
    if "title" in incoming:
        ticket["title"] = str(incoming["title"])[:200]
    if "description" in incoming:
        ticket["description"] = str(incoming["description"])[:10000]
    if "description_html" in incoming:
        ticket["description_html"] = _safe_html(incoming["description_html"])
    if "assigned_to" in incoming:
        ticket["assigned_to"] = str(incoming["assigned_to"])[:160]
    if "manager_username" in incoming:
        ticket["manager_username"] = str(incoming["manager_username"])[:160]
    if "field_values" in incoming and isinstance(incoming["field_values"], dict):
        ticket["field_values"] = ticket.get("field_values") or {}
        for k, v in incoming["field_values"].items():
            ticket["field_values"][k] = v
    if "allowed_users" in incoming:
        ticket["allowed_users"] = [
            str(u).strip() for u in incoming["allowed_users"] or []
        ]
    if "allowed_groups" in incoming:
        ticket["allowed_groups"] = [
            str(g).strip() for g in incoming["allowed_groups"] or []
        ]
    ticket["updated_at"] = _now()
    ticket.setdefault("history", []).append(
        {
            "at": _now(),
            "by": user.get("username"),
            "action": "updated",
        }
    )
    _save_store(store)
    return JSONResponse({"success": True, "ticket": ticket})


def _find_ticket_and_project(
    store: Dict[str, Any], ticket_id: str
) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    for project in store.get("projects", []):
        for ticket in project.get("tickets", []):
            if ticket.get("id") == ticket_id:
                return ticket, project
    return None, None


@router.get("/tickets/{ticket_id}")
async def get_ticket_by_id(ticket_id: str, request: Request):
    user = _require_feedback_access(request)
    store = _load_store()
    ticket, project = _find_ticket_and_project(store, ticket_id)
    if not ticket or not project:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if not _ticket_visible(project, ticket, user):
        raise HTTPException(status_code=403, detail="Access denied")
    return JSONResponse(
        {
            "success": True,
            "ticket": ticket,
            "project": {
                "id": project.get("id"),
                "title": project.get("title"),
                "key": project.get("key"),
                "icon": project.get("icon"),
                "workflow": project.get("workflow"),
                "form_fields": project.get("form_fields"),
            },
        }
    )


@router.post("/tickets/{ticket_id}/update")
async def update_ticket_direct(ticket_id: str, request: Request):
    user = _require_feedback_access(request)
    payload = await request.json()
    incoming = payload.get("ticket")
    if not isinstance(incoming, dict):
        raise HTTPException(status_code=400, detail="Ticket payload is required")
    store = _load_store()
    ticket, project = _find_ticket_and_project(store, ticket_id)
    if not ticket or not project:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if not _ticket_visible(project, ticket, user):
        raise HTTPException(status_code=403, detail="Access denied")

    # Check edit permission
    username = user.get("username")
    can_edit = (
        user.get("role") == "admin"
        or ticket.get("created_by") == username
        or ticket.get("assigned_to") == username
        or ticket.get("manager_username") == username
    )
    if not can_edit:
        raise HTTPException(status_code=403, detail="Permission denied")

    if "title" in incoming:
        ticket["title"] = str(incoming["title"])[:200]
    if "description" in incoming:
        ticket["description"] = str(incoming["description"])[:10000]
    if "description_html" in incoming:
        ticket["description_html"] = _safe_html(incoming["description_html"])
    if "assigned_to" in incoming:
        ticket["assigned_to"] = str(incoming["assigned_to"])[:160]
    if "manager_username" in incoming:
        ticket["manager_username"] = str(incoming["manager_username"])[:160]
    if "field_values" in incoming and isinstance(incoming["field_values"], dict):
        ticket.setdefault("field_values", {}).update(incoming["field_values"])
    if "allowed_users" in incoming:
        ticket["allowed_users"] = [
            str(u).strip() for u in incoming["allowed_users"] or []
        ]
    if "allowed_groups" in incoming:
        ticket["allowed_groups"] = [
            str(g).strip() for g in incoming["allowed_groups"] or []
        ]

    ticket["updated_at"] = _now()
    ticket.setdefault("history", []).append(
        {
            "at": _now(),
            "by": user.get("username"),
            "action": "updated",
        }
    )
    _save_store(store)
    return JSONResponse({"success": True, "ticket": ticket})


@router.post("/tickets/{ticket_id}/comments")
async def add_comment_direct(ticket_id: str, request: Request):
    user = _require_feedback_access(request)
    payload = await request.json()
    store = _load_store()
    ticket, project = _find_ticket_and_project(store, ticket_id)
    if not ticket or not project:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if not _ticket_visible(project, ticket, user):
        raise HTTPException(status_code=403, detail="Access denied")

    comment = {
        "id": f"comment_{secrets.token_hex(5)}",
        "author": user.get("username"),
        "body": str(payload.get("body") or "")[:10000],
        "body_html": _safe_html(payload.get("body_html")),
        "created_at": _now(),
    }
    if not comment["body"] and not comment["body_html"]:
        raise HTTPException(status_code=400, detail="Comment cannot be empty")
    ticket.setdefault("comments", []).append(comment)
    ticket["updated_at"] = _now()
    _save_store(store)
    return JSONResponse({"success": True, "comment": comment})


@router.post("/tickets/{ticket_id}/transition")
async def transition_ticket_direct(ticket_id: str, request: Request):
    user = _require_feedback_access(request)
    payload = await request.json()
    store = _load_store()
    ticket, project = _find_ticket_and_project(store, ticket_id)
    if not ticket or not project:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if not _ticket_visible(project, ticket, user):
        raise HTTPException(status_code=403, detail="Access denied")

    transition = next(
        (
            item
            for item in project.get("workflow", {}).get("transitions", [])
            if item.get("id") == payload.get("transition_id")
            and item.get("from_status") == ticket.get("status")
        ),
        None,
    )
    if not transition:
        raise HTTPException(status_code=400, detail="Transition is not available")
    if not _condition_matches(transition, ticket.get("field_values") or {}):
        raise HTTPException(status_code=400, detail="Transition condition is not met")
    if not _can_transition(transition, ticket, user):
        raise HTTPException(
            status_code=403,
            detail="Approval is required from the configured approver",
        )

    previous = ticket.get("status")
    ticket["status"] = transition.get("to_status")
    ticket["updated_at"] = _now()
    ticket.setdefault("history", []).append(
        {
            "at": _now(),
            "by": user.get("username"),
            "action": "transition",
            "transition": transition.get("name"),
            "from": previous,
            "to": ticket.get("status"),
        }
    )
    _save_store(store)
    return JSONResponse({"success": True, "ticket": ticket})


@router.post("/projects/{project_id}/hide")
async def hide_feedback_project(project_id: str, request: Request):
    _require_feedback_admin(request)
    payload = await request.json()
    hidden = bool(payload.get("hidden", True))
    store = _load_store()
    project = _find_project(store, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project["hidden"] = hidden
    project["updated_at"] = _now()
    _save_store(store)
    return JSONResponse({"success": True, "project": project})


@router.post("/tickets/{ticket_id}/hide")
async def hide_ticket_direct(ticket_id: str, request: Request):
    _require_feedback_admin(request)
    payload = await request.json()
    hidden = bool(payload.get("hidden", True))
    store = _load_store()
    ticket, project = _find_ticket_and_project(store, ticket_id)
    if not ticket or not project:
        raise HTTPException(status_code=404, detail="Ticket not found")
    ticket["hidden"] = hidden
    ticket["updated_at"] = _now()
    _save_store(store)
    return JSONResponse({"success": True, "ticket": ticket})


# ============ Evaluator Nomination & Approval System ============

EVALUATOR_STORE_PATH = (
    Path(os.getenv("APP_DATA_DIR", ".")).resolve()
    / "feedback_evaluator_nominations.json"
)


def _evaluator_store_path() -> Path:
    data_dir = Path(os.getenv("APP_DATA_DIR", ".")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "feedback_evaluator_nominations.json"


def _load_evaluator_store() -> Dict[str, Any]:
    conn = db.db_connect(db.get_db_file())
    try:
        rows = conn.execute("""
            SELECT id, nominator_username, manager_username, evaluators_json,
                   status, submitted_at, created_at, updated_at
            FROM feedback_evaluator_nominations
            ORDER BY created_at
            """).fetchall()
        nominations = []
        for row in rows:
            item = dict(row)
            item["evaluators"] = json.loads(item.pop("evaluators_json") or "[]")
            nominations.append(item)
        if nominations:
            return {"nominations": nominations}
    finally:
        conn.close()

    path = _evaluator_store_path()
    if path.exists():
        try:
            legacy = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(legacy, dict) and isinstance(legacy.get("nominations"), list):
                _save_evaluator_store(legacy)
                return legacy
        except Exception:
            pass
    return {"nominations": []}


def _save_evaluator_store(data: Dict[str, Any]) -> None:
    conn = db.db_connect(db.get_db_file())
    try:
        for nomination in data.get("nominations", []):
            conn.execute(
                """
                INSERT INTO feedback_evaluator_nominations (
                    id, nominator_username, manager_username, evaluators_json,
                    status, submitted_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    manager_username = excluded.manager_username,
                    evaluators_json = excluded.evaluators_json,
                    status = excluded.status,
                    submitted_at = excluded.submitted_at,
                    updated_at = excluded.updated_at
                """,
                (
                    nomination["id"],
                    nomination.get("nominator_username", ""),
                    nomination.get("manager_username", ""),
                    json.dumps(nomination.get("evaluators", []), ensure_ascii=False),
                    nomination.get("status", "pending"),
                    nomination.get("submitted_at"),
                    nomination.get("created_at") or _now(),
                    nomination.get("updated_at") or _now(),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _get_user_info(username: str) -> Dict[str, Any]:
    """Get user details from Employee Roster (SQL Server) or local database.
    Tries Employee Roster first (by email/username), then falls back to local DB.
    """
    # First try to get from Employee Roster using email
    try:
        emails = [username] if "@" in username else [f"{username}@snapp.cab"]
        for email in emails:
            emp = employee_roster.get_employee_by_email(email)
            if not emp:
                continue
            return {
                "username": emp.get("username", ""),
                "first_name": (
                    emp.get("full_name", "").split()[0] if emp.get("full_name") else ""
                ),
                "last_name": (
                    " ".join(emp.get("full_name", "").split()[1:])
                    if emp.get("full_name")
                    else ""
                ),
                "full_name": emp.get("e_full_name") or emp.get("full_name", ""),
                "e_full_name": emp.get("e_full_name", ""),
                "email": emp.get("email", ""),
                "role": "user",
                "modules": ["feedback_180"],
                "team": emp.get("team", ""),
                "sub_team": emp.get("sub_team", ""),
                "vertical": emp.get("vertical", ""),
                "sub_vertical": emp.get("sub_vertical", ""),
                "job_title": emp.get("job_title", ""),
                "manager_username": (
                    emp.get("line_manager_email", "").split("@")[0]
                    if emp.get("line_manager_email")
                    else ""
                ),
                "manager_email": emp.get("line_manager_email", ""),
                "line_manager_name": emp.get("line_manager_name", ""),
                "top_manager_email": emp.get("top_manager_email", ""),
                "active": emp.get("active", True),
            }
    except Exception as e:
        print(f"Employee roster lookup failed, falling back to local DB: {e}")

    # Fallback to local database
    conn = db.db_connect(db.get_db_file())
    try:
        row = conn.execute(
            """
            SELECT username, first_name, last_name, email, role, modules_json, department, manager_username
            FROM users
            WHERE username = ?
            """,
            (username,),
        ).fetchone()
        if row:
            return {
                "username": row["username"],
                "first_name": row["first_name"] or "",
                "last_name": row["last_name"] or "",
                "full_name": f"{row['first_name'] or ''} {row['last_name'] or ''}".strip()
                or row["username"],
                "email": row["email"] or "",
                "role": row["role"] or "user",
                "modules": (
                    json.loads(row["modules_json"]) if row["modules_json"] else []
                ),
                "team": row["department"] or "",
                "sub_team": "",
                "vertical": "",
                "job_title": "",
                "manager_username": row["manager_username"] or "",
            }
        return {}
    finally:
        conn.close()


def _search_users(query: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Search users by name, job title, team, or vertical.
    Uses the Employee Roster (SQL Server) as the primary source.
    Falls back to local database if roster is unavailable.
    """
    # Try to get users from Employee Roster (SQL Server)
    try:
        employees = employee_roster.search_employees(
            query=query, limit=limit, active_only=True
        )
        if employees:
            return [
                {
                    "username": emp.get("username", ""),
                    "full_name": emp.get("e_full_name") or emp.get("full_name", ""),
                    "e_full_name": emp.get("e_full_name", ""),
                    "email": emp.get("email", ""),
                    "team": emp.get("team", ""),
                    "vertical": emp.get("vertical", ""),
                    "job_title": emp.get("job_title", ""),
                    "manager_username": (
                        emp.get("line_manager_email", "").split("@")[0]
                        if emp.get("line_manager_email")
                        else ""
                    ),
                    "sub_team": emp.get("sub_team", ""),
                    "sub_vertical": emp.get("sub_vertical", ""),
                    "line_manager_name": emp.get("line_manager_name", ""),
                    "line_manager_email": emp.get("line_manager_email", ""),
                    "top_manager_email": emp.get("top_manager_email", ""),
                }
                for emp in employees
            ]
    except Exception as e:
        print(f"Employee roster search failed, falling back to local DB: {e}")

    # Fallback to local database
    conn = db.db_connect(db.get_db_file())
    try:
        pattern = f"%{query.strip()}%"
        rows = conn.execute(
            """
            SELECT username, first_name, last_name, email, department
            FROM users
            WHERE status = 'active' AND (
                first_name LIKE ? OR last_name LIKE ? OR username LIKE ? OR
                email LIKE ? OR department LIKE ?
            )
            ORDER BY first_name, last_name LIMIT ?
            """,
            (pattern, pattern, pattern, pattern, pattern, limit),
        ).fetchall()
        return [
            {
                "username": row["username"],
                "full_name": f"{row['first_name'] or ''} {row['last_name'] or ''}".strip()
                or row["username"],
                "email": row["email"] or "",
                "team": row["department"] or "",
                "sub_team": "",
                "vertical": "",
                "job_title": "",
                "manager_username": "",
            }
            for row in rows
        ]
    finally:
        conn.close()


@feedback_handlers.get("/evaluator-nomination/meta")
async def evaluator_nomination_meta(request: Request):
    """Get metadata for evaluator nomination system."""
    user = _require_feedback_access(request)
    user_info = _get_user_info(user.get("username", ""))
    manager_username = user_info.get("manager_username", "")
    manager_info = _get_user_info(manager_username) if manager_username else {}
    return JSONResponse(
        {
            "success": True,
            "current_user": user_info,
            "manager": manager_info,
            "permissions": {
                "can_nominate": True,
                "can_approve": True,
            },
        }
    )


@feedback_handlers.get("/evaluator-nomination/users/search")
async def search_evaluator_users(
    request: Request,
    q: str = "",
    team: str = "",
    sub_team: str = "",
    vertical: str = "",
):
    """Search users for evaluator selection - EMAIL ONLY."""
    _require_feedback_access(request)
    # Search with minimum 1 character for email
    if not any((q.strip(), team.strip(), sub_team.strip(), vertical.strip())):
        return JSONResponse({"success": True, "users": []})
    users = employee_roster.search_employees(
        query=q.strip(),
        limit=100,
        active_only=True,
        team=team.strip(),
        sub_team=sub_team.strip(),
        vertical=vertical.strip(),
        match_any=True,
    )
    return JSONResponse({"success": True, "users": users})


@feedback_handlers.get("/evaluator-nomination/users/filters")
async def evaluator_user_filters(request: Request):
    """Return roster dimensions used by the manager evaluator picker."""
    _require_feedback_access(request)
    return JSONResponse(
        {
            "success": True,
            "teams": employee_roster.get_all_teams(),
            "sub_teams": employee_roster.get_all_sub_teams(),
            "verticals": employee_roster.get_all_verticals(),
        }
    )


@feedback_handlers.get("/evaluator-nomination/my-nomination")
async def get_my_nomination(request: Request):
    """Get current user's nomination request."""
    user = _require_feedback_access(request)
    username = user.get("username", "")
    store = _load_evaluator_store()

    nomination = next(
        (
            n
            for n in store.get("nominations", [])
            if n.get("nominator_username") == username and n.get("status") != "closed"
        ),
        None,
    )

    if nomination:
        # Enrich with user info
        nominator_info = _get_user_info(nomination.get("nominator_username", ""))
        manager_info = _get_user_info(nomination.get("manager_username", ""))
        nomination["nominator_info"] = nominator_info
        nomination["manager_info"] = manager_info

        # Enrich evaluators with user info
        for eval_item in nomination.get("evaluators", []):
            lookup = eval_item.get("username") or eval_item.get("email", "")
            eval_info = _get_user_info(lookup)
            for key, value in eval_info.items():
                if value not in (None, "", []):
                    eval_item[key] = value

    return JSONResponse({"success": True, "nomination": nomination})


@feedback_handlers.get("/evaluator-nomination/history")
async def get_my_nomination_history(request: Request):
    """Return every evaluator nomination submitted by the current user."""
    user = _require_feedback_access(request)
    username = user.get("username", "")
    store = _load_evaluator_store()
    nominations = [
        nomination
        for nomination in store.get("nominations", [])
        if nomination.get("nominator_username") == username
    ]
    nominations.sort(
        key=lambda item: item.get("submitted_at") or item.get("created_at") or "",
        reverse=True,
    )
    for nomination in nominations:
        nomination["manager_info"] = _get_user_info(
            nomination.get("manager_username", "")
        )
        for evaluator in nomination.get("evaluators", []):
            evaluator_info = _get_user_info(
                evaluator.get("username") or evaluator.get("email", "")
            )
            for key, value in evaluator_info.items():
                if value not in (None, "", []):
                    evaluator[key] = value
    return JSONResponse({"success": True, "nominations": nominations})


@feedback_handlers.get("/evaluator-nomination/manager/requests")
async def get_manager_requests(request: Request):
    """Get nomination requests for manager approval."""
    user = _require_feedback_access(request)
    username = user.get("username", "")
    store = _load_evaluator_store()

    # Get all pending nominations assigned to this manager
    nominations = [
        n
        for n in store.get("nominations", [])
        if (user.get("role") == "admin" or n.get("manager_username") == username)
        and n.get("status") in ["pending", "partial"]
    ]

    # Enrich with user info
    for nomination in nominations:
        nominator_info = _get_user_info(nomination.get("nominator_username", ""))
        nomination["nominator_info"] = nominator_info

        for eval_item in nomination.get("evaluators", []):
            lookup = eval_item.get("username") or eval_item.get("email", "")
            eval_info = _get_user_info(lookup)
            for key, value in eval_info.items():
                if value not in (None, "", []):
                    eval_item[key] = value

    return JSONResponse({"success": True, "nominations": nominations})


@feedback_handlers.post("/evaluator-nomination/submit")
async def submit_evaluator_nomination(request: Request):
    """Submit evaluator nomination for manager approval."""
    user = _require_feedback_access(request)
    payload = await request.json()

    nominator_username = user.get("username", "")
    evaluators = payload.get("evaluators", [])
    manager_username = payload.get("manager_username", "")

    if not evaluators:
        raise HTTPException(
            status_code=400, detail="At least one evaluator is required"
        )

    if not manager_username:
        raise HTTPException(status_code=400, detail="Manager is required")

    # Validate each evaluator has a reason
    for eval_item in evaluators:
        if not eval_item.get("reason", "").strip():
            raise HTTPException(
                status_code=400,
                detail="Each evaluator must have a reason for nomination",
            )
        email = str(eval_item.get("email") or "").strip().lower()
        roster_user = employee_roster.get_employee_by_email(email) if email else None
        if not roster_user:
            raise HTTPException(
                status_code=400,
                detail=f"Evaluator {email or 'without email'} was not found in Employee Roster",
            )
        eval_item.update(
            {
                "username": roster_user.get("username", ""),
                "email": roster_user.get("email", ""),
                "full_name": roster_user.get("e_full_name")
                or roster_user.get("full_name", ""),
                "job_title": roster_user.get("job_title", ""),
                "team": roster_user.get("team", ""),
                "sub_team": roster_user.get("sub_team", ""),
                "vertical": roster_user.get("vertical", ""),
            }
        )

    store = _load_evaluator_store()

    # Check if user already has an active nomination
    existing = next(
        (
            n
            for n in store.get("nominations", [])
            if n.get("nominator_username") == nominator_username
            and n.get("status") != "closed"
        ),
        None,
    )

    if existing:
        manager_has_acted = any(
            evaluator.get("status") in {"approved", "rejected"}
            for evaluator in existing.get("evaluators", [])
        )
        if manager_has_acted:
            raise HTTPException(
                status_code=409,
                detail="This nomination can no longer be edited because the manager has already reviewed it.",
            )
        # Update existing nomination
        existing["evaluators"] = evaluators
        existing["manager_username"] = manager_username
        existing["status"] = "pending"
        existing["submitted_at"] = _now()
        existing["updated_at"] = _now()
        nomination = existing
    else:
        # Create new nomination
        nomination = {
            "id": f"NOM_{secrets.token_hex(6)}",
            "nominator_username": nominator_username,
            "manager_username": manager_username,
            "evaluators": evaluators,
            "status": "pending",
            "submitted_at": _now(),
            "created_at": _now(),
            "updated_at": _now(),
        }
        store.setdefault("nominations", []).append(nomination)

    _save_evaluator_store(store)
    return JSONResponse({"success": True, "nomination": nomination})


@feedback_handlers.post("/evaluator-nomination/{nomination_id}/approve-evaluator")
async def approve_evaluator(nomination_id: str, request: Request):
    """Approve a specific evaluator in a nomination."""
    user = _require_feedback_access(request)
    username = user.get("username", "")
    payload = await request.json()
    evaluator_username = payload.get("evaluator_username", "")

    store = _load_evaluator_store()
    nomination = next(
        (n for n in store.get("nominations", []) if n.get("id") == nomination_id), None
    )

    if not nomination:
        raise HTTPException(status_code=404, detail="Nomination not found")

    if user.get("role") != "admin" and nomination.get("manager_username") != username:
        raise HTTPException(
            status_code=403, detail="Only the assigned manager can approve"
        )

    # Find and update the evaluator
    for eval_item in nomination.get("evaluators", []):
        if eval_item.get("username") == evaluator_username:
            eval_item["status"] = "approved"
            eval_item["approved_by"] = username
            eval_item["approved_at"] = _now()
            eval_item.pop("rejected_by", None)
            eval_item.pop("rejected_at", None)
            eval_item.pop("rejection_reason", None)
            break

    # Check if all evaluators are processed
    all_processed = all(
        e.get("status") in ["approved", "rejected"]
        for e in nomination.get("evaluators", [])
    )

    # Create a ticket for the approved evaluator
    evaluator_info = next(
        (
            e
            for e in nomination.get("evaluators", [])
            if e.get("email") == evaluator_username
            or e.get("username") == evaluator_username
        ),
        None,
    )
    created_ticket = None
    if evaluator_info and evaluator_info.get("status") == "approved":
        # Find a feedback project to create the ticket in
        store = _load_store()
        feedback_projects = [
            p
            for p in store.get("projects", [])
            if p.get("key") and p.get("key").upper().startswith("FB")
        ]
        if feedback_projects:
            project = feedback_projects[0]
            project_id = project.get("id") or project.get("key")

            # Get evaluator username from email
            eval_email = evaluator_info.get("email", "")
            eval_username = (
                eval_email.split("@")[0] if "@" in eval_email else evaluator_username
            )

            # Create ticket for this evaluator
            # created_by = evaluator (so they can see it)
            # assigned_to = evaluator (so they can see it in their tickets)
            # manager_username = nominator (so the person who nominated can see it)
            tickets = project.setdefault("tickets", [])
            max_num = 100
            for t in tickets:
                tid = t.get("id", "")
                if "-" in tid:
                    try:
                        num = int(tid.split("-")[-1])
                        if num > max_num:
                            max_num = num
                    except ValueError:
                        pass
            next_num = max_num + 1
            project_key = _slug(
                project.get("key") or project.get("title") or "PROJ", "PROJ"
            ).upper()[:10]
            ticket_id = f"{project_key}-{next_num}"

            # Get evaluator's full name for the title
            eval_full_name = evaluator_info.get("full_name", "")
            eval_reason = evaluator_info.get("reason", "")

            ticket = {
                "id": ticket_id,
                "title": f"180 Feedback Evaluation: {eval_full_name or eval_username}",
                "description": f"Evaluation request for: {eval_full_name or eval_username}\nEmail: {eval_email}\n\nReason for nomination: {eval_reason or 'Not specified'}",
                "description_html": f"<p><strong>Evaluation request for:</strong> {eval_full_name or eval_username}</p><p><strong>Email:</strong> {eval_email}</p><p><strong>Reason for nomination:</strong> {eval_reason or 'Not specified'}</p>",
                "created_by": eval_username,
                "assigned_to": eval_username,
                "manager_username": nomination.get("nominator_username", ""),
                "status": "open",
                "field_values": {},
                "comments": [],
                "history": [
                    {
                        "at": _now(),
                        "by": username,
                        "action": f"Created from evaluator nomination approved by manager",
                    }
                ],
                "created_at": _now(),
                "updated_at": _now(),
                "evaluator_email": eval_email,
                "evaluator_reason": eval_reason,
            }
            project.setdefault("tickets", []).append(ticket)
            project["updated_at"] = _now()
            _save_store(store)
            created_ticket = ticket
            print(
                f"[FEEDBACK] Created ticket {ticket_id} for evaluator {eval_username} - visible to nominator {nomination.get('nominator_username', '')}"
            )

    nomination["status"] = "partial" if all_processed else "pending"

    nomination["updated_at"] = _now()
    _save_evaluator_store(store)

    return JSONResponse({"success": True, "nomination": nomination})


@feedback_handlers.post("/evaluator-nomination/{nomination_id}/reject-evaluator")
async def reject_evaluator(nomination_id: str, request: Request):
    """Reject a specific evaluator in a nomination."""
    user = _require_feedback_access(request)
    username = user.get("username", "")
    payload = await request.json()
    evaluator_username = payload.get("evaluator_username", "")
    rejection_reason = payload.get("reason", "")

    store = _load_evaluator_store()
    nomination = next(
        (n for n in store.get("nominations", []) if n.get("id") == nomination_id), None
    )

    if not nomination:
        raise HTTPException(status_code=404, detail="Nomination not found")

    if user.get("role") != "admin" and nomination.get("manager_username") != username:
        raise HTTPException(
            status_code=403, detail="Only the assigned manager can reject"
        )

    # Find and update the evaluator
    for eval_item in nomination.get("evaluators", []):
        if eval_item.get("username") == evaluator_username:
            eval_item["status"] = "rejected"
            eval_item["rejected_by"] = username
            eval_item["rejected_at"] = _now()
            eval_item["rejection_reason"] = rejection_reason
            eval_item.pop("approved_by", None)
            eval_item.pop("approved_at", None)
            break

    # Check if all evaluators are processed
    all_processed = all(
        e.get("status") in ["approved", "rejected"]
        for e in nomination.get("evaluators", [])
    )

    nomination["status"] = "partial" if all_processed else "pending"

    nomination["updated_at"] = _now()
    _save_evaluator_store(store)

    return JSONResponse({"success": True, "nomination": nomination})


@feedback_handlers.post("/evaluator-nomination/{nomination_id}/add-evaluator")
async def add_evaluator_as_manager(nomination_id: str, request: Request):
    """Manager adds a new evaluator to the nomination."""
    user = _require_feedback_access(request)
    username = user.get("username", "")
    payload = await request.json()

    evaluator_username = payload.get("evaluator_username", "")
    reason = payload.get("reason", "")

    if not evaluator_username or not reason:
        raise HTTPException(status_code=400, detail="Evaluator and reason are required")

    store = _load_evaluator_store()
    nomination = next(
        (n for n in store.get("nominations", []) if n.get("id") == nomination_id), None
    )

    if not nomination:
        raise HTTPException(status_code=404, detail="Nomination not found")

    if user.get("role") != "admin" and nomination.get("manager_username") != username:
        raise HTTPException(
            status_code=403, detail="Only the assigned manager can add evaluators"
        )

    evaluator_info = _get_user_info(evaluator_username)
    evaluator_email = evaluator_info.get("email", "")
    roster_user = (
        employee_roster.get_employee_by_email(evaluator_email)
        if evaluator_email
        else None
    )
    if not roster_user:
        raise HTTPException(
            status_code=400, detail="Evaluator was not found in Employee Roster"
        )
    if any(
        item.get("email") == roster_user.get("email")
        or item.get("username") == roster_user.get("username")
        for item in nomination.get("evaluators", [])
    ):
        raise HTTPException(status_code=409, detail="Evaluator is already in this list")

    # Add new evaluator
    new_evaluator = {
        "username": roster_user.get("username", ""),
        "email": roster_user.get("email", ""),
        "full_name": roster_user.get("e_full_name") or roster_user.get("full_name", ""),
        "job_title": roster_user.get("job_title", ""),
        "team": roster_user.get("team", ""),
        "sub_team": roster_user.get("sub_team", ""),
        "vertical": roster_user.get("vertical", ""),
        "reason": reason,
        "status": "approved",
        "added_by": username,
        "added_at": _now(),
        "approved_by": username,
        "approved_at": _now(),
    }
    nomination.setdefault("evaluators", []).append(new_evaluator)
    nomination["updated_at"] = _now()

    _save_evaluator_store(store)
    return JSONResponse({"success": True, "nomination": nomination})


@feedback_handlers.delete(
    "/evaluator-nomination/{nomination_id}/manager-added-evaluator/{evaluator_username}"
)
async def remove_manager_added_evaluator(
    nomination_id: str, evaluator_username: str, request: Request
):
    """Remove an evaluator that was added directly by the assigned manager."""
    user = _require_feedback_access(request)
    username = user.get("username", "")
    store = _load_evaluator_store()
    nomination = next(
        (n for n in store.get("nominations", []) if n.get("id") == nomination_id), None
    )

    if not nomination:
        raise HTTPException(status_code=404, detail="Nomination not found")
    if user.get("role") != "admin" and nomination.get("manager_username") != username:
        raise HTTPException(
            status_code=403,
            detail="Only the assigned manager can remove this evaluator",
        )

    evaluator = next(
        (
            item
            for item in nomination.get("evaluators", [])
            if item.get("username") == evaluator_username
        ),
        None,
    )
    if not evaluator:
        raise HTTPException(status_code=404, detail="Evaluator not found")
    if not evaluator.get("added_by"):
        raise HTTPException(
            status_code=400,
            detail="Only evaluators added by the manager can be removed here",
        )

    nomination["evaluators"] = [
        item
        for item in nomination.get("evaluators", [])
        if item.get("username") != evaluator_username
    ]
    nomination["updated_at"] = _now()
    _save_evaluator_store(store)
    return JSONResponse({"success": True, "nomination": nomination})


@feedback_handlers.post("/evaluator-nomination/{nomination_id}/close")
async def close_nomination(nomination_id: str, request: Request):
    """Close the nomination (manager action)."""
    user = _require_feedback_access(request)
    username = user.get("username", "")

    store = _load_evaluator_store()
    nomination = next(
        (n for n in store.get("nominations", []) if n.get("id") == nomination_id), None
    )

    if not nomination:
        raise HTTPException(status_code=404, detail="Nomination not found")

    if nomination.get("manager_username") != username:
        raise HTTPException(
            status_code=403,
            detail="Only the assigned manager can close this nomination",
        )

    # Check all evaluators are processed
    all_processed = all(
        e.get("status") in ["approved", "rejected"]
        for e in nomination.get("evaluators", [])
    )

    if not all_processed:
        raise HTTPException(
            status_code=400, detail="All evaluators must be processed before closing"
        )

    nomination["status"] = "closed"
    nomination["closed_at"] = _now()
    nomination["closed_by"] = username
    nomination["updated_at"] = _now()

    _save_evaluator_store(store)
    return JSONResponse({"success": True, "nomination": nomination})
