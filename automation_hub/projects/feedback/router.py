"""180 Feedback project module.

Module permissions:
- feedback_180: can open the module and submit/view assigned feedback cycles.
- feedback_180_admin: can configure cycles, workflow statuses, screens, participants and questions.
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

MODULE_KEY = "feedback_180"
ADMIN_MODULE_KEY = "feedback_180_admin"

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

FIELD_TYPES = {
    "single_line",
    "multi_line",
    "number",
    "date",
    "single_select",
    "multi_select",
    "user_picker",
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


def _default_screens() -> List[Dict[str, Any]]:
    return [
        {
            "id": "screen_setup",
            "name": "Setup screen",
            "description": "Admin defines objective, scale and participants.",
            "fields": ["title", "cycle", "deadline", "rating_scale"],
        },
        {
            "id": "screen_response",
            "name": "Reviewer response screen",
            "description": "Reviewer answers rating and text questions.",
            "fields": ["subject", "questions", "overall_comment"],
        },
        {
            "id": "screen_summary",
            "name": "Manager summary screen",
            "description": "Feedback admin reviews scores and coaching notes.",
            "fields": ["response_count", "average_score", "comments"],
        },
    ]


def _default_workflow() -> Dict[str, Any]:
    return {
        "scale_min": 1,
        "scale_max": 5,
        "anonymous": True,
        "deadline_days": 14,
        "statuses": [
            {
                "id": "draft",
                "name": "Draft",
                "category": "todo",
                "screen_id": "screen_setup",
                "description": "Cycle is being configured by 180 admin.",
            },
            {
                "id": "ready",
                "name": "Ready to launch",
                "category": "todo",
                "screen_id": "screen_setup",
                "description": "Participants and questions are approved.",
            },
            {
                "id": "collecting",
                "name": "Collecting feedback",
                "category": "doing",
                "screen_id": "screen_response",
                "description": "Reviewers can submit feedback.",
            },
            {
                "id": "calibration",
                "name": "Calibration",
                "category": "doing",
                "screen_id": "screen_summary",
                "description": "180 admin reviews response quality.",
            },
            {
                "id": "closed",
                "name": "Closed",
                "category": "done",
                "screen_id": "screen_summary",
                "description": "Cycle is complete.",
            },
        ],
        "screens": _default_screens(),
        "transitions": [
            {
                "id": "submit_for_approval",
                "name": "Submit for approval",
                "from_status": "draft",
                "to_status": "ready",
                "approver_type": "manager",
                "approver_value": "",
                "condition_field": "",
                "condition_operator": "equals",
                "condition_value": "",
            },
            {
                "id": "approve",
                "name": "Approve",
                "from_status": "ready",
                "to_status": "collecting",
                "approver_type": "feedback_admin",
                "approver_value": "",
                "condition_field": "",
                "condition_operator": "equals",
                "condition_value": "",
            },
        ],
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
        "label": str(field.get("label") or f"Field {index + 1}")[:160],
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
        "name": str(item.get("name") or f"Transition {index + 1}")[:120],
        "from_status": str(item.get("from_status") or "draft")[:80],
        "to_status": str(item.get("to_status") or "ready")[:80],
        "approver_type": approver_type,
        "approver_value": str(item.get("approver_value") or "")[:160],
        "condition_field": str(item.get("condition_field") or "")[:80],
        "condition_operator": str(item.get("condition_operator") or "equals")[:30],
        "condition_value": str(item.get("condition_value") or "")[:300],
    }


def _clean_status(status: Dict[str, Any], index: int) -> Dict[str, Any]:
    return {
        "id": str(status.get("id") or f"status_{secrets.token_hex(4)}")[:80],
        "name": str(status.get("name") or f"Status {index + 1}")[:100],
        "category": str(status.get("category") or "todo")[:40],
        "screen_id": str(status.get("screen_id") or "screen_response")[:80],
        "description": str(status.get("description") or "")[:500],
        "order": index,
    }


def _sanitize_project(
    project: Dict[str, Any],
    user: Dict[str, Any],
    existing: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    now = _now()
    clean = dict(project or {})
    clean["id"] = str(clean.get("id") or f"fb_{secrets.token_hex(6)}")
    clean["title"] = str(clean.get("title") or "180 Feedback Cycle")[:160]
    clean["description"] = str(clean.get("description") or "")[:1000]
    clean["cycle"] = str(clean.get("cycle") or "Quarterly")[:80]
    clean["status"] = str(clean.get("status") or "draft")[:80]
    clean["owner_username"] = (
        (existing or {}).get("owner_username") or user.get("username") or ""
    )
    clean["created_at"] = (
        (existing or {}).get("created_at") or clean.get("created_at") or now
    )
    clean["updated_at"] = now

    workflow = (
        clean.get("workflow")
        if isinstance(clean.get("workflow"), dict)
        else _default_workflow()
    )
    statuses = (
        workflow.get("statuses")
        if isinstance(workflow.get("statuses"), list)
        else _default_workflow()["statuses"]
    )
    screens = (
        workflow.get("screens")
        if isinstance(workflow.get("screens"), list)
        else _default_screens()
    )
    clean["workflow"] = {
        "scale_min": int(workflow.get("scale_min") or 1),
        "scale_max": int(workflow.get("scale_max") or 5),
        "anonymous": bool(workflow.get("anonymous", True)),
        "deadline_days": int(workflow.get("deadline_days") or 14),
        "statuses": [
            _clean_status(status, idx)
            for idx, status in enumerate(statuses[:20])
            if isinstance(status, dict)
        ],
        "screens": [
            {
                "id": str(screen.get("id") or f"screen_{idx + 1}")[:80],
                "name": str(screen.get("name") or f"Screen {idx + 1}")[:100],
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
            "category": str(q.get("category") or "General")[:80],
            "type": str(q.get("type") or "rating")[:40],
            "required": bool(q.get("required", True)),
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
    username = user.get("username") or ""
    participants = project.get("participants") or {}
    manages_ticket = any(
        ticket.get("manager_username") == username
        for ticket in project.get("tickets", [])
    )
    return (
        username in participants.get("reviewers", [])
        or username in participants.get("subjects", [])
        or project.get("owner_username") == username
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
    username = user.get("username") or ""
    return username in {
        ticket.get("created_by"),
        ticket.get("assigned_to"),
        ticket.get("manager_username"),
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
            "default_workflow": _default_workflow(),
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
    ticket = {
        "id": f"ticket_{secrets.token_hex(6)}",
        "title": str(incoming.get("title") or "Untitled ticket")[:200],
        "description": str(incoming.get("description") or "")[:10000],
        "description_html": _safe_html(incoming.get("description_html")),
        "created_by": user.get("username"),
        "assigned_to": str(incoming.get("assigned_to") or "")[:160],
        "manager_username": str(incoming.get("manager_username") or "")[:160],
        "status": str(
            incoming.get("status") or (statuses[0].get("id") if statuses else "draft")
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
