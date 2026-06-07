"""180 Feedback project module.

Module permissions:
- feedback_180: can open the module and submit/view assigned feedback cycles.
- feedback_180_admin: can configure cycles, workflow statuses, screens, participants and questions.
"""

from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from automation_hub.core import auth

MODULE_KEY = "feedback_180"
ADMIN_MODULE_KEY = "feedback_180_admin"

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


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
    return (
        username in participants.get("reviewers", [])
        or username in participants.get("subjects", [])
        or project.get("owner_username") == username
    )


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
        }
    )


@router.get("/projects")
async def list_feedback_projects(request: Request):
    user = _require_feedback_access(request)
    store = _load_store()
    projects = [p for p in store.get("projects", []) if _project_visible(p, user)]
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
