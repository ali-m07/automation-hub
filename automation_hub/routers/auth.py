# Authentication routes: login, logout, 2FA, user profile
# Uses automation_hub.core only (no app import to avoid circular deps).

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from automation_hub.core import audit, auth, constants, db
from automation_hub.core.notifications import send_signup_notification
from automation_hub.services.email_service import EmailService
from automation_hub.services.enterprise_auth import (
    authenticate_ldap,
    ldap_enabled,
    oidc_config,
    oidc_enabled,
    provision_user,
)

try:
    import pyotp
except ImportError:
    pyotp = None

try:
    from automation_hub.core.redis_util import redis_available, rate_limit_check
except ImportError:

    def redis_available() -> bool:
        return False

    def rate_limit_check(key: str, limit: int, window_seconds: int):
        return (True, 0, None)


def _db():
    conn = db.db_connect(db.get_db_file())
    return conn


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _user_agent(request: Request) -> str:
    return (request.headers.get("user-agent") or "")[:500]


def _rate_limit_abort(
    request: Request, scope: str, identifier: str, limit: int, window_seconds: int = 60
) -> None:
    """If Redis is available and limit exceeded, raise HTTP 429."""
    if not redis_available():
        return
    key = f"{scope}:{identifier}"
    allowed, count, retry_after = rate_limit_check(key, limit, window_seconds)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Try again later.",
            headers={"Retry-After": str(retry_after or 60)},
        )


def _log_login_failure(username: Optional[str], request: Request, reason: str) -> None:
    """Log failed login attempts for later stats (per user)."""
    try:
        conn = _db()
        try:
            conn.execute(
                "INSERT INTO login_fail_log (username, attempted_at, ip_address, user_agent, reason) VALUES (?,?,?,?,?)",
                (
                    username or "",
                    db.utc_now_iso(),
                    _client_ip(request),
                    _user_agent(request),
                    reason,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        # Do not block login flow if logging fails
        pass


# Page router: GET /login
from fastapi import APIRouter

page_router = APIRouter(tags=["auth"])


@page_router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """
    Login page.
    First screen: username + password; if 2FA enabled, step=2fa shows TOTP code form.
    """
    user = auth.get_current_user(request)
    if user:
        return RedirectResponse(url="/", status_code=302)
    step = request.query_params.get("step")
    pending_2fa_username = request.session.get("pending_2fa") if step == "2fa" else None
    templates = getattr(request.app.state, "templates", None)
    if not templates:
        return JSONResponse({"error": "Templates not available"}, status_code=500)
    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context={
            "request": request,
            "step_2fa": step == "2fa",
            "pending_2fa_username": pending_2fa_username or "",
            "msg": request.query_params.get("msg"),
            "ldap_enabled": ldap_enabled(),
            "oidc_enabled": oidc_enabled(),
            "oidc_provider_name": oidc_config()["name"],
        },
    )


# API router: POST /login, POST /login-2fa, GET /logout, GET /api/me, POST /api/me/*, public auth APIs
auth_router = APIRouter(tags=["auth"])


@auth_router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    """Login: update last_login_at, log login, store session_version for logout-all support."""
    username = (username or "").strip()
    password = (password or "").strip()
    ip = _client_ip(request)
    _rate_limit_abort(request, "login_ip", ip, 10, 60)

    # Normal DB-backed authentication for all users
    conn = _db()
    try:
        cur = conn.execute(
            "SELECT username,password,role,level,modules_json,status,session_version,totp_secret,totp_enabled FROM users WHERE username = ?",
            (username,),
        )
        row = cur.fetchone()
        # row is already a RowDict (dict-like) from db_connect's row_factory, so use it directly
        record = dict(row) if row else None
    finally:
        conn.close()

    # اما همچنان رکورد واقعی DB را برای session_version و role استفاده می‌کنیم.
    valid_local = bool(
        record and auth.verify_password(password, record.get("password") or "")
    )
    if not valid_local and ldap_enabled():
        try:
            record = authenticate_ldap(username, password)
        except Exception:
            record = None
    if not record:
        _log_login_failure(username, request, "invalid_credentials")
        return RedirectResponse(url="/login?error=invalid", status_code=302)

    if (record.get("status") or "") == "pending":
        _log_login_failure(username, request, "status_pending")
        return RedirectResponse(url="/login?error=pending", status_code=302)

    if not auth.is_password_hash(record.get("password") or ""):
        conn = _db()
        try:
            conn.execute(
                "UPDATE users SET password = ? WHERE username = ?",
                (auth.hash_password(password), username),
            )
            conn.commit()
        finally:
            conn.close()

    # 2FA: if TOTP enabled, require second factor before setting session
    # در محیط تست می‌توانیم با ENV غیرفعال کنیم (ENABLE_2FA=1 برای فعال بودن).
    enable_2fa = os.getenv("ENABLE_2FA", "0").lower() in ("1", "true", "yes")
    if enable_2fa:
        totp_enabled = bool(record.get("totp_enabled"))
        if totp_enabled and record.get("totp_secret") and pyotp:
            request.session["pending_2fa"] = username
            return RedirectResponse(url="/login?step=2fa", status_code=302)

    now = db.utc_now_iso()
    conn = _db()
    try:
        conn.execute(
            "UPDATE users SET last_login_at = ? WHERE username = ?",
            (now, username),
        )
        conn.execute(
            "INSERT INTO login_log(username,logged_at,ip_address,user_agent) VALUES (?,?,?,?)",
            (username, now, _client_ip(request), _user_agent(request)),
        )
        conn.commit()
    finally:
        conn.close()

    modules = auth.user_modules_from_record(record)
    session_version = (
        record.get("session_version")
        if record.get("session_version") is not None
        else 0
    )
    request.session["user"] = {
        "username": record.get("username") or username,
        "role": record.get("role") or "user",
        "level": record.get("level") or "user",
        "modules": modules,
        "session_version": session_version,
    }

    audit.audit_log(username, "login", details={"ip": _client_ip(request)})

    if (record.get("role") or "") == "admin":
        return RedirectResponse(url="/admin", status_code=302)
    return RedirectResponse(url="/", status_code=302)


@auth_router.get("/auth/oidc/login")
async def oidc_login(request: Request):
    if not oidc_enabled():
        raise HTTPException(status_code=404, detail="OIDC is not enabled")
    from authlib.integrations.starlette_client import OAuth

    config = oidc_config()
    oauth = OAuth()
    client = oauth.register(
        name="enterprise",
        client_id=config["client_id"],
        client_secret=config["client_secret"],
        server_metadata_url=config["discovery_url"],
        client_kwargs={"scope": config["scope"]},
    )
    redirect_uri = str(request.url_for("oidc_callback"))
    return await client.authorize_redirect(request, redirect_uri)


@auth_router.get("/auth/oidc/callback", name="oidc_callback")
async def oidc_callback(request: Request):
    if not oidc_enabled():
        raise HTTPException(status_code=404, detail="OIDC is not enabled")
    from authlib.integrations.starlette_client import OAuth

    config = oidc_config()
    oauth = OAuth()
    client = oauth.register(
        name="enterprise",
        client_id=config["client_id"],
        client_secret=config["client_secret"],
        server_metadata_url=config["discovery_url"],
        client_kwargs={"scope": config["scope"]},
    )
    token = await client.authorize_access_token(request)
    claims = token.get("userinfo") or await client.userinfo(token=token)
    username = claims.get("email") or claims.get("preferred_username")
    record = provision_user(
        username or "",
        "oidc",
        str(claims.get("sub") or ""),
        str(claims.get("given_name") or ""),
        str(claims.get("family_name") or ""),
    )
    if record.get("status") != "active":
        return RedirectResponse(url="/login?error=inactive", status_code=302)
    request.session["user"] = {
        "username": record["username"],
        "role": record.get("role") or "user",
        "level": record.get("level") or "user",
        "modules": auth.user_modules_from_record(record),
        "session_version": record.get("session_version") or 0,
    }
    audit.audit_log(record["username"], "oidc_login")
    return RedirectResponse(url="/", status_code=302)


@auth_router.post("/api/signup")
async def api_signup(request: Request):
    """Public signup endpoint used by login page JS."""
    _rate_limit_abort(request, "signup_ip", _client_ip(request), 20, 60)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"success": False, "error": "Invalid JSON payload"}, status_code=400
        )

    email = (body.get("username") or body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    first_name = (body.get("first_name") or "").strip()
    last_name = (body.get("last_name") or "").strip()

    # Validate email and password strength
    email_err = auth.validate_email_username(email)
    if email_err:
        return JSONResponse({"success": False, "error": email_err}, status_code=400)

    pw_err = auth.validate_password_strength(password)
    if pw_err:
        return JSONResponse({"success": False, "error": pw_err}, status_code=400)

    if not first_name or not last_name:
        return JSONResponse(
            {"success": False, "error": "First name and last name are required"},
            status_code=400,
        )

    now = db.utc_now_iso()
    conn = _db()
    try:
        # Check for existing user
        row = conn.execute(
            "SELECT username FROM users WHERE username = ?",
            (email,),
        ).fetchone()
        if row:
            return JSONResponse(
                {
                    "success": False,
                    "error": "An account with this email already exists",
                },
                status_code=400,
            )

        # Create user in pending status; admin must approve from Admin panel
        conn.execute(
            """
            INSERT INTO users(username,password,role,level,modules_json,email,status,first_name,last_name,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                email,
                auth.hash_password(password),
                "user",
                "user",
                "[]",
                email,
                "pending",
                first_name,
                last_name,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    # Fire signup notification asynchronously (best-effort; ignore failures)
    try:
        email_service = EmailService()
        send_signup_notification(email, first_name, last_name, now, email_service)
    except Exception:
        # Do not fail signup if notifications are misconfigured
        pass

    return JSONResponse(
        {
            "success": True,
            "message": "Account created. Your request is pending admin approval.",
        }
    )


@auth_router.post("/login-2fa")
async def login_2fa(request: Request, code: str = Form(...)):
    """Complete login after TOTP verification."""
    _rate_limit_abort(request, "login_ip", _client_ip(request), 10, 60)
    username = request.session.get("pending_2fa")
    if not username:
        _log_login_failure(None, request, "2fa_no_pending_session")
        return RedirectResponse(url="/login?error=invalid", status_code=302)
    if not pyotp:
        request.session.pop("pending_2fa", None)
        _log_login_failure(username, request, "2fa_unavailable")
        return RedirectResponse(url="/login?error=2fa_unavailable", status_code=302)
    conn = _db()
    try:
        row = conn.execute(
            "SELECT username,role,level,modules_json,session_version,totp_secret,totp_enabled FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    finally:
        conn.close()
    if (
        not row
        or not db.safe_row_get(row, "totp_enabled")
        or not db.safe_row_get(row, "totp_secret")
    ):
        request.session.pop("pending_2fa", None)
        _log_login_failure(username, request, "2fa_not_enabled_or_missing_secret")
        return RedirectResponse(url="/login?error=invalid", status_code=302)
    totp = pyotp.TOTP(row["totp_secret"])
    if not totp.verify(code.strip().replace(" ", ""), valid_window=1):
        _log_login_failure(username, request, "2fa_bad_code")
        return RedirectResponse(url="/login?step=2fa&error=bad_code", status_code=302)
    request.session.pop("pending_2fa", None)
    now = db.utc_now_iso()
    conn = _db()
    try:
        conn.execute(
            "UPDATE users SET last_login_at = ? WHERE username = ?", (now, username)
        )
        conn.execute(
            "INSERT INTO login_log(username,logged_at,ip_address,user_agent) VALUES (?,?,?,?)",
            (username, now, _client_ip(request), _user_agent(request)),
        )
        conn.commit()
    finally:
        conn.close()
    modules = auth.user_modules_from_record(row)
    request.session["user"] = {
        "username": row["username"],
        "role": row["role"],
        "level": row["level"],
        "modules": modules,
        "session_version": row["session_version"] or 0,
    }
    audit.audit_log(username, "login", details={"ip": _client_ip(request), "2fa": True})
    if row["role"] == "admin":
        return RedirectResponse(url="/admin", status_code=302)
    return RedirectResponse(url="/", status_code=302)


@auth_router.get("/logout")
async def logout(request: Request):
    """Clear session and go back to login page"""
    user = auth.get_current_user(request)
    if user:
        audit.audit_log(user.get("username"), "logout")
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


# User profile API routes
profile_router = APIRouter(prefix="/api/me", tags=["auth"])


@profile_router.get("")
async def me(request: Request):
    """Return current user info (used by frontend), including first_name, last_name, email from DB."""
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse({"authenticated": False})
    conn = _db()
    try:
        row = conn.execute(
            "SELECT first_name, last_name, email, department, manager_username FROM users WHERE username = ?",
            (user["username"],),
        ).fetchone()
    finally:
        conn.close()
    if row:
        user = {
            **user,
            "first_name": db.safe_row_get(row, "first_name") or "",
            "last_name": db.safe_row_get(row, "last_name") or "",
            "email": db.safe_row_get(row, "email") or user.get("username", ""),
            "department": db.safe_row_get(row, "department") or "",
            "manager_username": db.safe_row_get(row, "manager_username") or "",
        }
    return JSONResponse({"authenticated": True, "user": user})


@profile_router.post("/update")
async def me_update(request: Request, payload: Dict[str, Any]):
    """Update current user profile (first_name, last_name, email)."""
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    first_name = (payload.get("first_name") or "").strip()
    last_name = (payload.get("last_name") or "").strip()
    email = (payload.get("email") or "").strip()
    conn = _db()
    try:
        conn.execute(
            "UPDATE users SET first_name = ?, last_name = ?, email = ? WHERE username = ?",
            (first_name, last_name, email, user["username"]),
        )
        conn.commit()
    finally:
        conn.close()
    return JSONResponse({"success": True})


@profile_router.post("/change-password")
async def me_change_password(request: Request, payload: Dict[str, Any]):
    """Change current user password (current_password, new_password)."""
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    current = payload.get("current_password") or ""
    new_pass = payload.get("new_password") or ""
    if not new_pass or len(new_pass) < 12:
        raise HTTPException(
            status_code=400, detail="New password must be at least 12 characters"
        )
    conn = _db()
    try:
        row = conn.execute(
            "SELECT password FROM users WHERE username = ?", (user["username"],)
        ).fetchone()
    finally:
        conn.close()
    if not row or not auth.verify_password(
        current, db.safe_row_get(row, "password") or ""
    ):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    err = auth.validate_password_strength(new_pass)
    if err:
        raise HTTPException(status_code=400, detail=err)
    conn = _db()
    try:
        conn.execute(
            "UPDATE users SET password = ? WHERE username = ?",
            (auth.hash_password(new_pass), user["username"]),
        )
        conn.commit()
    finally:
        conn.close()
    audit.audit_log(user["username"], "password_changed")
    return JSONResponse({"success": True})


# 2FA routes
@profile_router.get("/2fa/status")
async def twofa_status(request: Request):
    """Return whether 2FA is enabled for the current user."""
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    conn = _db()
    try:
        row = conn.execute(
            "SELECT totp_enabled FROM users WHERE username = ?",
            (user["username"],),
        ).fetchone()
    finally:
        conn.close()
    enabled = bool(row and row["totp_enabled"]) if row else False
    return JSONResponse({"enabled": enabled})


@profile_router.post("/2fa/setup")
async def twofa_setup(request: Request):
    """Generate a new TOTP secret and return provisioning_uri for QR. Does not enable until verify."""
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    if not pyotp:
        raise HTTPException(status_code=503, detail="2FA not available")
    secret = pyotp.random_base32()
    conn = _db()
    try:
        conn.execute(
            "UPDATE users SET totp_secret = ?, totp_enabled = 0 WHERE username = ?",
            (secret, user["username"]),
        )
        conn.commit()
    finally:
        conn.close()
    totp = pyotp.TOTP(secret)
    issuer = os.getenv("APP_NAME", "Servexa")
    provisioning_uri = totp.provisioning_uri(name=user["username"], issuer_name=issuer)
    return JSONResponse({"secret": secret, "provisioning_uri": provisioning_uri})


@profile_router.post("/2fa/verify")
async def twofa_verify(request: Request, payload: Dict[str, Any]):
    """Verify TOTP code and enable 2FA for current user."""
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    if not pyotp:
        raise HTTPException(status_code=503, detail="2FA not available")
    code = (payload.get("code") or "").strip().replace(" ", "")
    conn = _db()
    try:
        row = conn.execute(
            "SELECT totp_secret FROM users WHERE username = ?",
            (user["username"],),
        ).fetchone()
    finally:
        conn.close()
    if not row or not row["totp_secret"]:
        raise HTTPException(status_code=400, detail="Run setup first")
    totp = pyotp.TOTP(row["totp_secret"])
    if not totp.verify(code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid code")
    conn = _db()
    try:
        conn.execute(
            "UPDATE users SET totp_enabled = 1 WHERE username = ?",
            (user["username"],),
        )
        conn.commit()
    finally:
        conn.close()
    audit.audit_log(user["username"], "2fa_enabled")
    return JSONResponse({"success": True})


@profile_router.post("/2fa/disable")
async def twofa_disable(request: Request, payload: Dict[str, Any]):
    """Disable 2FA; requires current TOTP code or password."""
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    code = (payload.get("code") or "").strip().replace(" ", "")
    conn = _db()
    try:
        row = conn.execute(
            "SELECT totp_secret, totp_enabled FROM users WHERE username = ?",
            (user["username"],),
        ).fetchone()
    finally:
        conn.close()
    if not row or not row["totp_enabled"]:
        return JSONResponse({"success": True})
    if not pyotp:
        raise HTTPException(status_code=503, detail="2FA not available")
    totp = pyotp.TOTP(row["totp_secret"])
    if not totp.verify(code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid code")
    conn = _db()
    try:
        conn.execute(
            "UPDATE users SET totp_secret = NULL, totp_enabled = 0 WHERE username = ?",
            (user["username"],),
        )
        conn.commit()
    finally:
        conn.close()
    audit.audit_log(user["username"], "2fa_disabled")
    return JSONResponse({"success": True})


@profile_router.get("/preferences")
async def get_preferences(request: Request):
    """Get user preferences (onboarding, language, etc)."""
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    conn = _db()
    try:
        row = conn.execute(
            "SELECT has_seen_onboarding, language FROM user_preferences WHERE username = ?",
            (user["username"],),
        ).fetchone()
    finally:
        conn.close()
    if row:
        return JSONResponse(
            {
                "has_seen_onboarding": bool(row["has_seen_onboarding"]),
                "language": row["language"] or "en",
            }
        )
    return JSONResponse({"has_seen_onboarding": False, "language": "en"})


@profile_router.post("/preferences")
async def update_preferences(request: Request, payload: Dict[str, Any]):
    """Update user preferences."""
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    has_seen_onboarding = bool(payload.get("has_seen_onboarding", False))
    language = (payload.get("language") or "en").strip()[:10]
    now = db.utc_now_iso()
    conn = _db()
    try:
        conn.execute(
            """
            INSERT INTO user_preferences (username, has_seen_onboarding, language, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (username) DO UPDATE SET
                has_seen_onboarding = EXCLUDED.has_seen_onboarding,
                language = EXCLUDED.language,
                updated_at = EXCLUDED.updated_at
            """,
            (user["username"], 1 if has_seen_onboarding else 0, language, now),
        )
        conn.commit()
    finally:
        conn.close()
    return JSONResponse({"success": True})
