from __future__ import annotations

import hashlib
import json
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from fastapi.requests import Request

from . import db as _db


def user_modules_from_record(record: Any) -> List[str]:
    """Parse modules_json from a user row (dict-like)."""
    try:
        raw = _db.safe_row_get(record, "modules_json", "[]")
        data = json.loads(raw or "[]")
        if isinstance(data, list):
            return [str(x) for x in data]
    except Exception:
        pass
    return []


_SESSION_CACHE: Dict[str, Tuple[Dict[str, Any], float]] = {}


def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """Return current user from session, leveraging a fast TTL cache to avoid hitting the DB every request."""
    user = request.session.get("user")
    if not user or not user.get("username"):
        return None

    username = user["username"]
    now = time.time()

    # 1. Check fast memory cache (10 seconds TTL)
    cached = _SESSION_CACHE.get(username)
    if cached and cached[1] > now:
        cdata = cached[0]
        if user.get("session_version") != cdata["session_version"]:
            request.session.clear()
            # Invalidate cache if session is bad
            _SESSION_CACHE.pop(username, None)
            return None

        request.session["user"] = {
            **user,
            "username": username,
            "role": cdata["role"],
            "level": cdata["level"],
            "status": cdata["status"],
            "modules": cdata["modules"],
            "session_version": cdata["session_version"],
        }
        return request.session["user"]

    # 2. Cache miss or expired: Sync DB check
    conn = _db.db_connect(_db.get_db_file())
    try:
        row = conn.execute(
            "SELECT username, role, level, modules_json, session_version, status FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if not row:
            request.session.clear()
            _SESSION_CACHE.pop(username, None)
            return None

        sess_ver = _db.safe_row_get(row, "session_version")
        if user.get("session_version") != sess_ver:
            request.session.clear()
            _SESSION_CACHE.pop(username, None)
            return None

        db_role = (_db.safe_row_get(row, "role") or "user").strip().lower()
        db_level = (_db.safe_row_get(row, "level") or "user").strip().lower()
        db_status = (_db.safe_row_get(row, "status") or "active").strip().lower()
        modules = user_modules_from_record(row)

        # 3. Update cache (TTL 10 seconds)
        _SESSION_CACHE[username] = (
            {
                "role": db_role,
                "level": db_level,
                "status": db_status,
                "modules": modules,
                "session_version": sess_ver,
            },
            now + 10.0,
        )

        # Clean up cache if it grows too large (very basic bounded cleanup)
        if len(_SESSION_CACHE) > 5000:
            keys_to_del = [k for k, v in _SESSION_CACHE.items() if v[1] < now]
            for k in keys_to_del:
                _SESSION_CACHE.pop(k, None)

        request.session["user"] = {
            **user,
            "username": _db.safe_row_get(row, "username") or username,
            "role": db_role,
            "level": db_level,
            "status": db_status,
            "modules": modules,
            "session_version": sess_ver,
        }
        return request.session["user"]
    finally:
        conn.close()


def user_has_module(user: Dict[str, Any], module_key: str) -> bool:
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    return module_key in (user.get("modules") or [])


def require_module(
    request: Request, module_key: str, get_current_user
) -> Dict[str, Any]:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user.get("role") == "admin":
        return user
    if module_key not in (user.get("modules") or []):
        raise HTTPException(status_code=403, detail="Access denied")
    return user


def require_admin(request: Request, get_current_user) -> Dict[str, Any]:
    user = get_current_user(request)
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def require_any_module(
    request: Request, module_keys: List[str], get_current_user
) -> Dict[str, Any]:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user.get("role") == "admin":
        return user
    mods = set(user.get("modules") or [])
    if not any(k in mods for k in module_keys):
        raise HTTPException(status_code=403, detail="Access denied")
    return user


def get_api_key_user(request: Request) -> Optional[Dict[str, Any]]:
    """Get user from API key in Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    api_key = auth_header[7:].strip()
    if not api_key:
        return None
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    conn = _db.db_connect(_db.get_db_file())
    try:
        row = conn.execute(
            """
            SELECT id, owner_username, scopes_json, revoked_at
            FROM api_keys
            WHERE key_hash = ? AND revoked_at IS NULL
            """,
            (key_hash,),
        ).fetchone()
        if not row:
            return None
        # Update last_used_at
        conn.execute(
            "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
            (_db.utc_now_iso(), row["id"]),
        )
        conn.commit()
        scopes = json.loads(row["scopes_json"] or "[]")
        return {
            "username": row["owner_username"],
            "api_key_id": row["id"],
            "scopes": scopes,
        }
    finally:
        conn.close()


def generate_api_key() -> str:
    """Generate a new API key."""
    return f"ah_{secrets.token_urlsafe(32)}"


# Password hashing (passlib)
try:
    from passlib.context import CryptContext

    _PWD_CONTEXT = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
except ImportError:
    _PWD_CONTEXT = None


def is_password_hash(value: str) -> bool:
    if not value:
        return False
    if value.startswith("$pbkdf2-sha256$"):
        return True
    return (
        value.startswith("$2a$") or value.startswith("$2b$") or value.startswith("$2y$")
    )


def hash_password(password: str) -> str:
    if not _PWD_CONTEXT:
        raise RuntimeError("passlib not installed")
    return _PWD_CONTEXT.hash(password)


def verify_password(plain_password: str, stored_password: str) -> bool:
    if not _PWD_CONTEXT:
        return plain_password == stored_password
    if is_password_hash(stored_password):
        return _PWD_CONTEXT.verify(plain_password, stored_password)
    return plain_password == stored_password


def validate_password_strength(password: str) -> Optional[str]:
    if not password:
        return "Password is required"
    if " " in password:
        return "Password cannot contain spaces"
    if len(password) < 12:
        return "Password must be at least 12 characters"
    if not any(c.islower() for c in password):
        return "Password must include at least one lowercase letter"
    if not any(c.isupper() for c in password):
        return "Password must include at least one uppercase letter"
    if not any(c.isdigit() for c in password):
        return "Password must include at least one digit"
    if not any(not c.isalnum() for c in password):
        return "Password must include at least one symbol"
    return None


def validate_email_username(username: str) -> Optional[str]:
    u = (username or "").strip().lower()
    if not u:
        return "Email is required"
    if " " in u:
        return "Username cannot contain spaces"
    if u.count("@") != 1:
        return "Username must be an email address"
    local, domain = u.split("@", 1)
    if not local or not domain:
        return "Username must be an email address"
    if "." not in domain:
        return "Email must include a valid domain"
    if domain.startswith(".") or domain.endswith("."):
        return "Email must include a valid domain"
    return None


def normalize_user_status(s: str) -> str:
    s = (s or "").strip().lower()
    if s in ("active", "inactive", "pending"):
        return s
    return ""
