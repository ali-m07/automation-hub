"""Standalone Feedback API routes.

This router owns the public Feedback API namespace. Ticketing and project
workflow routes live under /api/ticketing.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from automation_hub.core import auth, db
from automation_hub.projects.ticketing import router as legacy

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.get("/evaluator-nomination/settings")
async def evaluator_nomination_settings(request: Request):
    auth.require_admin(request, auth.get_current_user)
    return JSONResponse({"success": True, **legacy._deadline_state()})


@router.post("/evaluator-nomination/settings")
async def save_evaluator_nomination_settings(request: Request):
    auth.require_admin(request, auth.get_current_user)
    payload = await request.json()
    raw_deadline = str(payload.get("deadline") or "").strip()
    normalized = ""
    if raw_deadline:
        try:
            parsed = datetime.fromisoformat(raw_deadline.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            normalized = parsed.astimezone(timezone.utc).isoformat()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid deadline") from exc
    conn = db.db_connect(db.get_db_file())
    try:
        conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
            ("feedback_nomination_deadline", normalized),
        )
        conn.commit()
    finally:
        conn.close()
    return JSONResponse({"success": True, **legacy._deadline_state()})

router.add_api_route(
    "/evaluator-nomination/meta",
    legacy.evaluator_nomination_meta,
    methods=["GET"],
)
router.add_api_route(
    "/evaluator-nomination/users/search",
    legacy.search_evaluator_users,
    methods=["GET"],
)
router.add_api_route(
    "/evaluator-nomination/users/filters",
    legacy.evaluator_user_filters,
    methods=["GET"],
)
router.add_api_route(
    "/evaluator-nomination/my-nomination",
    legacy.get_my_nomination,
    methods=["GET"],
)
router.add_api_route(
    "/evaluator-nomination/history",
    legacy.get_my_nomination_history,
    methods=["GET"],
)
router.add_api_route(
    "/evaluator-nomination/manager/requests",
    legacy.get_manager_requests,
    methods=["GET"],
)
router.add_api_route(
    "/evaluator-nomination/submit",
    legacy.submit_evaluator_nomination,
    methods=["POST"],
)
router.add_api_route(
    "/evaluator-nomination/{nomination_id}/approve-evaluator",
    legacy.approve_evaluator,
    methods=["POST"],
)
router.add_api_route(
    "/evaluator-nomination/{nomination_id}/reject-evaluator",
    legacy.reject_evaluator,
    methods=["POST"],
)
router.add_api_route(
    "/evaluator-nomination/{nomination_id}/add-evaluator",
    legacy.add_evaluator_as_manager,
    methods=["POST"],
)
router.add_api_route(
    "/evaluator-nomination/{nomination_id}/remove-manager-added-evaluator",
    legacy.remove_manager_added_evaluator,
    methods=["POST"],
)
router.add_api_route(
    "/evaluator-nomination/{nomination_id}/close",
    legacy.close_nomination,
    methods=["POST"],
)
