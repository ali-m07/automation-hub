"""Standalone Feedback API routes.

This router owns the public Feedback API namespace. Ticketing and project
workflow routes live under /api/ticketing.
"""

from fastapi import APIRouter

from automation_hub.projects.ticketing import router as legacy

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

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
