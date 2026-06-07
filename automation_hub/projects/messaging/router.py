from __future__ import annotations

import json
import secrets
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlencode
import os

import pandas as pd
from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import JSONResponse, RedirectResponse, Response

from automation_hub.core import auth, db, notifications
from automation_hub.core.settings import get_upload_limits
from automation_hub.core.validation import check_upload_size

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


router = APIRouter(prefix="/api", tags=["messaging"])


@router.post("/send-emails")
async def send_emails(
    request: Request,
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    password: str = Form(...),
    data_file_id: str = Form(...),
    subject: str = Form(...),
    image_option: str = Form(...),
    smtp_server: str = Form("smtp.example.com"),
    smtp_port: int = Form(587),
    image_folder_id: Optional[str] = Form(None),
    image_upload_id: Optional[str] = Form(None),
    image_link: Optional[str] = Form(None),
    to_column: str = Form(...),
    img_column: Optional[str] = Form(None),
    cc_columns: Optional[str] = Form(None),  # JSON string
):
    """Send bulk emails with images."""
    auth.require_module(request, "messaging_send", auth.get_current_user)
    try:
        data_path = UPLOAD_DIR / data_file_id
        if not data_path.exists():
            raise HTTPException(status_code=404, detail="Data file not found")

        # Parse CC columns
        cc_columns_list = json.loads(cc_columns) if cc_columns else []

        # Get image folder or upload path
        image_folder = None
        attached_image_path = None

        if image_option == "1":  # One image for all
            if image_upload_id:
                attached_image_path = str(UPLOAD_DIR / image_upload_id)
        elif image_option == "2":  # Relationship-based
            if image_folder_id:
                image_folder = str(UPLOAD_DIR / image_folder_id)

        user = auth.get_current_user(request)
        from automation_hub.services.job_queue import (
            create_job,
            enqueue_job,
            store_job_secret,
        )

        payload = {
            "email": email,
            "data_path": str(data_path),
            "subject": subject,
            "image_folder": image_folder,
            "attached_image_path": attached_image_path,
            "image_link": image_link,
            "to_column": to_column,
            "img_column": img_column,
            "cc_columns": cc_columns_list,
            "smtp_server": smtp_server,
            "smtp_port": smtp_port,
        }
        queue_id = create_job(
            (user or {}).get("username", "anonymous"),
            "bulk_email",
            payload,
        )
        store_job_secret(queue_id, "smtp_password", password)
        enqueue_job(queue_id)

        return JSONResponse(
            {
                "success": True,
                "job_id": queue_id,
                "message": f"Email job queued. Poll /api/jobs/{queue_id}",
            },
            status_code=202,
        )

    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-smtp")
async def test_smtp(request: Request):
    """Test SMTP connection."""
    auth.require_module(request, "messaging_send", auth.get_current_user)
    try:
        data = await request.json()
        email = data.get("email")
        password = data.get("password")
        smtp_server = data.get("smtp_server", "smtp.example.com")
        smtp_port = int(data.get("smtp_port", 587))

        if not email or not password:
            return JSONResponse(
                {"success": False, "error": "Email and password are required"},
                status_code=400,
            )

        import smtplib

        try:
            server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
            server.starttls()
            server.login(email, password)
            server.quit()
            return JSONResponse(
                {"success": True, "message": "SMTP connection successful"}
            )
        except smtplib.SMTPAuthenticationError as e:
            return JSONResponse(
                {"success": False, "error": f"Authentication failed: {str(e)}"},
                status_code=401,
            )
        except smtplib.SMTPException as e:
            return JSONResponse(
                {"success": False, "error": f"SMTP error: {str(e)}"}, status_code=500
            )
        except Exception as e:
            return JSONResponse(
                {"success": False, "error": f"Connection failed: {str(e)}"},
                status_code=500,
            )

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/upload-image")
async def upload_image(file: UploadFile = File(...)):
    """Upload image for email attachment."""
    try:
        safe_filename = os.path.basename(file.filename.replace("\\", "/"))
        file_path = UPLOAD_DIR / f"image_{safe_filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return JSONResponse({"success": True, "file_id": file_path.name})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-image-folder")
async def upload_image_folder(request: Request, files: List[UploadFile] = File(...)):
    """Upload multiple images as a folder (for messaging or creative usage)."""
    check_upload_size(request)
    _, max_files = get_upload_limits()
    if len(files) > max_files:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files. Maximum is {max_files} per request.",
        )
    try:
        folder_id = f"folder_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}"
        folder_path = UPLOAD_DIR / folder_id
        folder_path.mkdir(exist_ok=True)

        uploaded_files = []
        for file in files:
            safe_filename = os.path.basename(file.filename.replace("\\", "/"))
            file_path = folder_path / safe_filename
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            uploaded_files.append(safe_filename)

        return JSONResponse(
            {"success": True, "folder_id": folder_id, "files": uploaded_files}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _db():
    conn = db.db_connect(db.get_db_file())
    return conn


def _now_iso() -> str:
    return db.utc_now_iso()


@router.get("/campaigns")
async def list_campaigns(request: Request):
    """List email campaigns for current user."""
    auth.require_module(request, "messaging_send", auth.get_current_user)
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )
    username = user.get("username") or ""
    conn = _db()
    try:
        rows = conn.execute(
            """
            SELECT id, name, subject, status, scheduled_at, created_at, sent_at, total_recipients
            FROM email_campaigns
            WHERE created_by = ?
            ORDER BY created_at DESC
            LIMIT 100
            """,
            (username,),
        ).fetchall()
    finally:
        conn.close()
    campaigns = [
        {
            "id": r["id"],
            "name": r["name"],
            "subject": r["subject"],
            "status": r["status"],
            "scheduled_at": r["scheduled_at"],
            "created_at": r["created_at"],
            "sent_at": r["sent_at"],
            "total_recipients": r["total_recipients"] or 0,
        }
        for r in rows
    ]
    return JSONResponse({"success": True, "campaigns": campaigns})


@router.post("/campaigns")
async def create_campaign(request: Request):
    """Create a new email campaign."""
    auth.require_module(request, "messaging_send", auth.get_current_user)
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )
    body: Dict[str, Any] = await request.json()
    name = (body.get("name") or "").strip()
    subject = (body.get("subject") or "").strip()
    template_html = body.get("template_html") or ""
    scheduled_at = body.get("scheduled_at")  # ISO string or None
    if not name or not subject:
        return JSONResponse(
            {"success": False, "error": "name and subject required"}, status_code=400
        )
    username = user.get("username") or ""
    now = _now_iso()
    conn = _db()
    try:
        conn.execute(
            """
            INSERT INTO email_campaigns (name, subject, template_html, status, scheduled_at, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (name, subject, template_html, "draft", scheduled_at, username, now),
        )
        row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
        campaign_id = row["id"]
        conn.commit()
    finally:
        conn.close()
    return JSONResponse({"success": True, "campaign_id": campaign_id})


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: int, request: Request):
    """Get campaign details."""
    auth.require_module(request, "messaging_send", auth.get_current_user)
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )
    username = user.get("username") or ""
    conn = _db()
    try:
        row = conn.execute(
            "SELECT * FROM email_campaigns WHERE id = ? AND created_by = ?",
            (campaign_id, username),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return JSONResponse(
            {"success": False, "error": "Campaign not found"}, status_code=404
        )
    campaign = db.row_to_dict(row)
    # Get stats
    conn = _db()
    try:
        stats_row = conn.execute(
            """
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as sent,
                SUM(CASE WHEN opened_at IS NOT NULL THEN 1 ELSE 0 END) as opened,
                SUM(CASE WHEN clicked_at IS NOT NULL THEN 1 ELSE 0 END) as clicked
            FROM campaign_recipients
            WHERE campaign_id = ?
            """,
            (campaign_id,),
        ).fetchone()
    finally:
        conn.close()
    stats = {
        "total": stats_row["total"] or 0,
        "sent": stats_row["sent"] or 0,
        "opened": stats_row["opened"] or 0,
        "clicked": stats_row["clicked"] or 0,
    }
    campaign["stats"] = stats
    return JSONResponse({"success": True, "campaign": campaign})


@router.post("/campaigns/{campaign_id}/send")
async def send_campaign(
    campaign_id: int, request: Request, background_tasks: BackgroundTasks
):
    """Send campaign immediately or schedule it."""
    auth.require_module(request, "messaging_send", auth.get_current_user)
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )
    body: Dict[str, Any] = await request.json()
    send_now = body.get("send_now", True)
    recipient_list_id = body.get("recipient_list_id")
    segment_filter = body.get("segment_filter")  # JSON filter
    username = user.get("username") or ""
    conn = _db()
    try:
        row = conn.execute(
            "SELECT * FROM email_campaigns WHERE id = ? AND created_by = ?",
            (campaign_id, username),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return JSONResponse(
            {"success": False, "error": "Campaign not found"}, status_code=404
        )
    campaign = db.row_to_dict(row)
    # Load recipients from list or segment
    recipients = []
    if recipient_list_id:
        conn = _db()
        try:
            rec_rows = conn.execute(
                "SELECT email, name FROM contacts WHERE list_id = ?",
                (recipient_list_id,),
            ).fetchall()
            recipients = [{"email": r["email"], "name": r["name"]} for r in rec_rows]
        finally:
            conn.close()
    # Store recipients in campaign_recipients
    now = _now_iso()
    conn = _db()
    try:
        for rec in recipients:
            conn.execute(
                """
                INSERT INTO campaign_recipients (campaign_id, email, name, status, created_at)
                VALUES (?, ?, ?, 'pending', ?)
                """,
                (campaign_id, rec["email"], rec.get("name"), now),
            )
        conn.execute(
            "UPDATE email_campaigns SET status = ?, total_recipients = ? WHERE id = ?",
            ("sending" if send_now else "scheduled", len(recipients), campaign_id),
        )
        conn.commit()
    finally:
        conn.close()
    if send_now:
        # Send in background
        background_tasks.add_task(_send_campaign_emails, campaign_id, campaign)
    return JSONResponse({"success": True, "message": "Campaign queued"})


def _send_campaign_emails(campaign_id: int, campaign: Dict[str, Any]) -> None:
    """Background task to send campaign emails."""
    conn = _db()
    try:
        recipients = conn.execute(
            "SELECT id, email, name FROM campaign_recipients WHERE campaign_id = ? AND status = 'pending'",
            (campaign_id,),
        ).fetchall()
        # Use email service to send
        # For now, just mark as sent (full implementation would use EmailService)
        now = _now_iso()
        for rec in recipients:
            conn.execute(
                "UPDATE campaign_recipients SET status = 'sent', sent_at = ? WHERE id = ?",
                (now, rec["id"]),
            )
        conn.execute(
            "UPDATE email_campaigns SET status = 'completed', sent_at = ? WHERE id = ?",
            (now, campaign_id),
        )
        conn.commit()
    finally:
        conn.close()


@router.get("/campaigns/{campaign_id}/track/open/{recipient_id}")
async def track_open(campaign_id: int, recipient_id: int):
    """Track email open (1x1 pixel)."""
    conn = _db()
    try:
        conn.execute(
            "UPDATE campaign_recipients SET opened_at = ? WHERE id = ? AND campaign_id = ?",
            (_now_iso(), recipient_id, campaign_id),
        )
        conn.commit()
    finally:
        conn.close()
    # Return 1x1 transparent pixel
    pixel = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
    return Response(content=pixel, media_type="image/png")


import hmac
import hashlib
import os
from urllib.parse import unquote


def _verify_redirect_url(url: str, signature: str) -> bool:
    secret_value = os.getenv("SECRET_KEY") or os.getenv("SESSION_SECRET")
    if not secret_value:
        return False
    secret = secret_value.encode()
    expected = hmac.new(secret, url.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.get("/campaigns/{campaign_id}/track/click/{recipient_id}")
async def track_click(
    campaign_id: int, recipient_id: int, url: str = Query(...), sig: str = Query(None)
):
    """Track email click and redirect."""
    decoded_url = unquote(url)

    # Prevent Open Redirect: allow relative URLs, require valid signature for absolute ones
    is_relative = decoded_url.startswith("/") and not decoded_url.startswith("//")
    if not is_relative:
        if not sig or not _verify_redirect_url(decoded_url, sig):
            # Invalid signature or external URL without signature -> Default to home
            decoded_url = "/"

    conn = _db()
    try:
        conn.execute(
            "UPDATE campaign_recipients SET clicked_at = ? WHERE id = ? AND campaign_id = ?",
            (_now_iso(), recipient_id, campaign_id),
        )
        conn.commit()
    finally:
        conn.close()
    # Redirect to original or safe URL
    return RedirectResponse(url=decoded_url)


@router.get("/contact-lists")
async def list_contact_lists(request: Request):
    """List contact lists for current user."""
    auth.require_module(request, "messaging_send", auth.get_current_user)
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )
    username = user.get("username") or ""
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT id, name, created_at FROM contact_lists WHERE owner_username = ? ORDER BY created_at DESC",
            (username,),
        ).fetchall()
    finally:
        conn.close()
    lists = [
        {"id": r["id"], "name": r["name"], "created_at": r["created_at"]} for r in rows
    ]
    return JSONResponse({"success": True, "lists": lists})


@router.post("/contact-lists")
async def create_contact_list(request: Request):
    """Create a new contact list."""
    auth.require_module(request, "messaging_send", auth.get_current_user)
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )
    body: Dict[str, Any] = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        return JSONResponse(
            {"success": False, "error": "name required"}, status_code=400
        )
    username = user.get("username") or ""
    now = _now_iso()
    conn = _db()
    try:
        conn.execute(
            "INSERT INTO contact_lists (name, owner_username, created_at) VALUES (?, ?, ?)",
            (name, username, now),
        )
        row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
        list_id = row["id"]
        conn.commit()
    finally:
        conn.close()
    return JSONResponse({"success": True, "list_id": list_id})


@router.post("/contact-lists/{list_id}/contacts")
async def add_contacts(list_id: int, request: Request):
    """Add contacts to a list."""
    auth.require_module(request, "messaging_send", auth.get_current_user)
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(
            {"success": False, "error": "Authentication required"}, status_code=401
        )
    body: Dict[str, Any] = await request.json()
    contacts = body.get("contacts") or []
    if not contacts:
        return JSONResponse(
            {"success": False, "error": "contacts array required"}, status_code=400
        )
    username = user.get("username") or ""
    conn = _db()
    try:
        # Verify ownership
        list_row = conn.execute(
            "SELECT id FROM contact_lists WHERE id = ? AND owner_username = ?",
            (list_id, username),
        ).fetchone()
        if not list_row:
            return JSONResponse(
                {"success": False, "error": "List not found"}, status_code=404
            )
        now = _now_iso()
        for contact in contacts:
            email = (contact.get("email") or "").strip()
            name = (contact.get("name") or "").strip()
            if email:
                conn.execute(
                    "INSERT INTO contacts (list_id, email, name, created_at) VALUES (?, ?, ?, ?)",
                    (list_id, email, name, now),
                )
        conn.commit()
    finally:
        conn.close()
    return JSONResponse({"success": True})
