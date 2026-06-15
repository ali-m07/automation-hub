"""Standalone Feedback API routes.

This router owns the public Feedback API namespace. Ticketing and project
workflow routes live under /api/ticketing.
"""

from datetime import datetime, timezone
from io import BytesIO

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo

from automation_hub.core import auth, db
from automation_hub.projects.ticketing import router as legacy

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ROWS = 500
IMPORT_HEADERS = ("email", "reason")


def _xlsx_response(workbook: Workbook, filename: str) -> StreamingResponse:
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _style_header(sheet, cell_range: str) -> None:
    fill = PatternFill("solid", fgColor="D9F3EA")
    font = Font(bold=True, color="21413A")
    for row in sheet[cell_range]:
        for cell in row:
            cell.fill = fill
            cell.font = font
            cell.alignment = Alignment(vertical="center")


@router.get("/evaluator-nomination/template.xlsx")
async def evaluator_nomination_template(request: Request):
    legacy._require_feedback_access(request)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Evaluators"
    sheet.append(list(IMPORT_HEADERS))
    sheet.append(["person@snapp.cab", "Worked closely on the same project"])
    sheet.freeze_panes = "A2"
    sheet.column_dimensions["A"].width = 34
    sheet.column_dimensions["B"].width = 64
    _style_header(sheet, "A1:B1")
    table = Table(displayName="EvaluatorImport", ref="A1:B2")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2",
        showRowStripes=True,
        showColumnStripes=False,
    )
    sheet.add_table(table)

    guide = workbook.create_sheet("Instructions")
    guide.append(["Servexa evaluator import template"])
    guide.append(["1", "Keep the email and reason headers unchanged."])
    guide.append(["2", "Use one evaluator per row."])
    guide.append(["3", "Email must exist in the Employee Roster."])
    guide.append(["4", "Reason is required."])
    guide.append(["5", f"Maximum {MAX_IMPORT_ROWS} evaluators per file."])
    guide.column_dimensions["A"].width = 8
    guide.column_dimensions["B"].width = 72
    guide["A1"].font = Font(bold=True, size=15, color="21413A")
    guide.merge_cells("A1:B1")
    return _xlsx_response(workbook, "servexa-evaluator-template.xlsx")


@router.post("/evaluator-nomination/import")
async def import_evaluator_nomination(request: Request, file: UploadFile = File(...)):
    user = legacy._require_feedback_access(request)
    legacy._require_nomination_window_open()
    filename = str(file.filename or "").lower()
    if not filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Please upload an .xlsx file")
    content = await file.read(MAX_IMPORT_BYTES + 1)
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(
            status_code=413, detail="Excel file must be 5 MB or smaller"
        )
    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
        sheet = (
            workbook["Evaluators"]
            if "Evaluators" in workbook.sheetnames
            else workbook.active
        )
        rows = sheet.iter_rows(values_only=True)
        raw_headers = next(rows, None)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid Excel workbook") from exc
    if not raw_headers:
        raise HTTPException(status_code=400, detail="The workbook is empty")
    headers = [str(value or "").strip().lower() for value in raw_headers]
    if headers[:2] != list(IMPORT_HEADERS):
        raise HTTPException(
            status_code=400,
            detail="Use the Servexa template with email and reason columns",
        )

    imported = []
    errors = []
    seen = set()
    historical = legacy._previous_evaluator_keys(user.get("username", ""))
    for excel_row, values in enumerate(rows, start=2):
        email = str(values[0] or "").strip().lower() if values else ""
        reason = str(values[1] or "").strip() if len(values or ()) > 1 else ""
        if not email and not reason:
            continue
        if len(imported) >= MAX_IMPORT_ROWS:
            errors.append(f"Row {excel_row}: maximum {MAX_IMPORT_ROWS} rows exceeded")
            break
        identity = legacy._identity_key(email)
        if not email or not reason:
            errors.append(f"Row {excel_row}: email and reason are required")
            continue
        if identity in seen:
            errors.append(f"Row {excel_row}: duplicate email in this file")
            continue
        if identity in historical:
            errors.append(f"Row {excel_row}: evaluator was nominated previously")
            continue
        roster_user = legacy.employee_roster.get_employee_by_email(email)
        if not roster_user:
            errors.append(f"Row {excel_row}: {email} was not found in Employee Roster")
            continue
        seen.add(identity)
        imported.append(
            {
                "username": roster_user.get("username", ""),
                "email": roster_user.get("email", ""),
                "full_name": roster_user.get("e_full_name")
                or roster_user.get("full_name", ""),
                "job_title": roster_user.get("job_title", ""),
                "team": roster_user.get("team", ""),
                "sub_team": roster_user.get("sub_team", ""),
                "vertical": roster_user.get("vertical", ""),
                "reason": reason,
                "status": "pending",
            }
        )
    if not imported:
        raise HTTPException(
            status_code=400,
            detail=errors[0] if errors else "No valid evaluator rows were found",
        )
    return JSONResponse({"success": True, "evaluators": imported, "errors": errors})


@router.get("/evaluator-nomination/export.xlsx")
async def export_evaluator_nominations(request: Request):
    user = legacy._require_feedback_access(request)
    current_username = legacy._identity_key(user.get("username", ""))
    is_admin = user.get("role") == "admin"
    nominations = legacy._load_evaluator_store().get("nominations", [])
    if not is_admin:
        nominations = [
            item
            for item in nominations
            if legacy._identity_key(item.get("manager_username")) == current_username
        ]

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Nominations"
    headers = [
        "Nomination ID",
        "Nominator",
        "Nominator Email",
        "Nominator Team",
        "Sub-team",
        "Vertical",
        "Manager",
        "Submitted At",
        "Request Status",
        "Evaluator",
        "Evaluator Email",
        "Evaluator Team",
        "Evaluator Sub-team",
        "Evaluator Vertical",
        "Reason",
        "Evaluator Status",
    ]
    sheet.append(headers)
    for nomination in nominations:
        nominator = legacy._get_user_info(nomination.get("nominator_username", ""))
        for evaluator in nomination.get("evaluators", []):
            sheet.append(
                [
                    nomination.get("id", ""),
                    nominator.get("full_name", ""),
                    nominator.get("email") or nomination.get("nominator_username", ""),
                    nominator.get("team", ""),
                    nominator.get("sub_team", ""),
                    nominator.get("vertical", ""),
                    nomination.get("manager_username", ""),
                    nomination.get("submitted_at", ""),
                    nomination.get("status", ""),
                    evaluator.get("full_name", ""),
                    evaluator.get("email", ""),
                    evaluator.get("team", ""),
                    evaluator.get("sub_team", ""),
                    evaluator.get("vertical", ""),
                    evaluator.get("reason", ""),
                    evaluator.get("status", "pending"),
                ]
            )
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    _style_header(sheet, f"A1:P1")
    widths = [20, 26, 32, 24, 22, 22, 28, 25, 18, 26, 32, 24, 22, 22, 48, 18]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[chr(64 + index)].width = width
    filename = (
        "servexa-all-feedback-nominations.xlsx"
        if is_admin
        else "servexa-my-team-feedback-nominations.xlsx"
    )
    return _xlsx_response(workbook, filename)


@router.get("/evaluator-nomination/settings")
async def evaluator_nomination_settings(request: Request):
    auth.require_admin(request, auth.get_current_user)
    return JSONResponse(
        {
            "success": True,
            "user": legacy._deadline_state(),
            "manager": legacy._manager_deadline_state(),
        }
    )


@router.post("/evaluator-nomination/settings")
async def save_evaluator_nomination_settings(request: Request):
    auth.require_admin(request, auth.get_current_user)
    payload = await request.json()
    deadlines = {}
    for field, setting_key in (
        ("user_deadline", "feedback_nomination_deadline"),
        ("manager_deadline", "feedback_manager_deadline"),
    ):
        raw_deadline = str(payload.get(field) or "").strip()
        normalized = ""
        if raw_deadline:
            try:
                parsed = datetime.fromisoformat(raw_deadline.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                normalized = parsed.astimezone(timezone.utc).isoformat()
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Invalid deadline") from exc
        deadlines[setting_key] = normalized
    conn = db.db_connect(db.get_db_file())
    try:
        for setting_key, value in deadlines.items():
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                (setting_key, value),
            )
        conn.commit()
    finally:
        conn.close()
    return JSONResponse(
        {
            "success": True,
            "user": legacy._deadline_state(),
            "manager": legacy._manager_deadline_state(),
        }
    )


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
