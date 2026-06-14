"""Active Directory/LDAP and OIDC user provisioning."""

from __future__ import annotations

import json
import os
import secrets
from typing import Any, Dict, List, Optional

from automation_hub.core import auth, db


def enabled(name: str) -> bool:
    return _setting(name, "").strip().lower() in {"1", "true", "yes", "on"}


_SETTING_KEYS = {
    "LDAP_ENABLED": "ldap_enabled",
    "LDAP_SERVERS": "ldap_servers",
    "LDAP_SERVER": "ldap_server",
    "LDAP_PORT": "ldap_port",
    "LDAP_USE_SSL": "ldap_use_ssl",
    "LDAP_BASE_DN": "ldap_base_dn",
    "LDAP_USER_BASE_DN": "ldap_user_base_dn",
    "LDAP_GROUP_BASE_DN": "ldap_group_base_dn",
    "LDAP_BIND_USER": "ldap_bind_dn",
    "LDAP_BIND_PASSWORD": "ldap_bind_password",
    "LDAP_USER_PRINCIPAL": "ldap_user_principal",
    "LDAP_USER_FILTER": "ldap_user_filter",
    "LDAP_DIRECTORY_FILTER": "ldap_directory_filter",
}


def _setting(name: str, default: str = "") -> str:
    """Read runtime LDAP settings from Admin UI first, then environment."""
    key = _SETTING_KEYS.get(name)
    if key:
        conn = db.db_connect(db.get_db_file())
        try:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?", (key,)
            ).fetchone()
            value = db.safe_row_get(row, "value")
            if value not in (None, ""):
                return str(value)
        finally:
            conn.close()
    return os.getenv(name, default)


def _servers() -> List[str]:
    raw = _setting("LDAP_SERVERS") or _setting("LDAP_SERVER")
    return [item.strip() for item in raw.replace("\n", ",").split(",") if item.strip()]


def oidc_enabled() -> bool:
    return enabled("OIDC_ENABLED") and bool(os.getenv("OIDC_DISCOVERY_URL"))


def ldap_enabled() -> bool:
    return enabled("LDAP_ENABLED") and bool(_servers())


def _default_modules() -> list[str]:
    raw = os.getenv("SSO_DEFAULT_MODULES", "feedback_180")
    return [item.strip() for item in raw.split(",") if item.strip()]


def provision_user(
    username: str,
    provider: str,
    subject: str = "",
    first_name: str = "",
    last_name: str = "",
    email: str = "",
    department: str = "",
) -> Dict[str, Any]:
    """Create or refresh an externally authenticated local user record."""
    username = username.strip().lower()
    if not username:
        raise ValueError("Identity provider did not return a username")
    now = db.utc_now_iso()
    conn = db.db_connect(db.get_db_file())
    try:
        row = conn.execute(
            "SELECT username,role,level,modules_json,status,session_version FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if not row:
            conn.execute(
                """
                INSERT INTO users (
                    username, password, role, level, modules_json, email, status,
                    first_name, last_name, department, created_at, auth_provider, external_subject
                ) VALUES (?, ?, 'user', 'user', ?, ?, 'active', ?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    auth.hash_password(secrets.token_urlsafe(32)),
                    json.dumps(_default_modules()),
                    email or username,
                    first_name,
                    last_name,
                    department,
                    now,
                    provider,
                    subject,
                ),
            )
        else:
            modules = auth.user_modules_from_record(row)
            if "feedback" in modules and "feedback_180" not in modules:
                modules = [
                    "feedback_180" if item == "feedback" else item for item in modules
                ]
            conn.execute(
                """
                UPDATE users SET auth_provider = ?, external_subject = ?,
                    first_name = COALESCE(NULLIF(?, ''), first_name),
                    last_name = COALESCE(NULLIF(?, ''), last_name),
                    email = COALESCE(NULLIF(?, ''), email),
                    department = COALESCE(NULLIF(?, ''), department),
                    modules_json = ?
                WHERE username = ?
                """,
                (
                    provider,
                    subject,
                    first_name,
                    last_name,
                    email,
                    department,
                    json.dumps(modules),
                    username,
                ),
            )
        conn.commit()
        refreshed = conn.execute(
            """
            SELECT username,role,level,modules_json,status,session_version,
                   auth_provider,external_subject
            FROM users WHERE username = ?
            """,
            (username,),
        ).fetchone()
        return dict(refreshed)
    finally:
        conn.close()


def authenticate_ldap(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticate against LDAP/Active Directory and provision the user."""
    if not ldap_enabled() or not password:
        return None
    from ldap3 import ALL, Connection, Server, SUBTREE

    server = Server(
        _servers()[0],
        port=int(_setting("LDAP_PORT", "636")),
        use_ssl=enabled("LDAP_USE_SSL"),
        get_info=ALL,
        connect_timeout=10,
    )
    user_principal = _setting("LDAP_USER_PRINCIPAL", "{username}").format(
        username=username
    )
    connection = Connection(
        server,
        user=user_principal,
        password=password,
        auto_bind=True,
        receive_timeout=10,
    )
    try:
        base_dn = _setting("LDAP_USER_BASE_DN") or _setting("LDAP_BASE_DN")
        search_filter = _setting(
            "LDAP_USER_FILTER", "(sAMAccountName={username})"
        ).format(username=username.replace("\\", "").replace("*", ""))
        connection.search(
            base_dn,
            search_filter,
            search_scope=SUBTREE,
            attributes=["mail", "userPrincipalName", "givenName", "sn", "displayName", "department", "objectGUID"],
            size_limit=1,
        )
        if not connection.entries:
            return None
        entry = connection.entries[0]
        email = str(entry.mail or entry.userPrincipalName or username)
        return provision_user(
            email,
            "ldap",
            str(entry.objectGUID or entry.entry_dn),
            str(entry.givenName or ""),
            str(entry.sn or ""),
            email,
            str(entry.department or ""),
        )
    finally:
        connection.unbind()


def search_ldap_users(query: str) -> List[Dict[str, str]]:
    """Search Active Directory using a configured service account."""
    if not ldap_enabled() or not _setting("LDAP_BIND_USER"):
        return []
    from ldap3 import ALL, Connection, Server, SUBTREE
    from ldap3.utils.conv import escape_filter_chars

    server = Server(
        _servers()[0],
        port=int(_setting("LDAP_PORT", "636")),
        use_ssl=enabled("LDAP_USE_SSL"),
        get_info=ALL,
        connect_timeout=10,
    )
    connection = Connection(
        server,
        user=_setting("LDAP_BIND_USER"),
        password=_setting("LDAP_BIND_PASSWORD"),
        auto_bind=True,
        receive_timeout=10,
    )
    try:
        term = escape_filter_chars(query.strip() or "*")
        if term != "*":
            term = f"*{term}*"
        template = _setting(
            "LDAP_DIRECTORY_FILTER",
            "(&(objectClass=user)(|(sAMAccountName={query})(displayName={query})(mail={query})))",
        )
        connection.search(
            _setting("LDAP_USER_BASE_DN") or _setting("LDAP_BASE_DN"),
            template.format(query=term),
            search_scope=SUBTREE,
            attributes=["sAMAccountName", "displayName", "mail", "userPrincipalName", "department"],
            size_limit=50,
        )
        return [
            {
                "id": str(entry.sAMAccountName or entry.userPrincipalName),
                "username": str(entry.sAMAccountName or entry.userPrincipalName),
                "label": str(entry.displayName or entry.sAMAccountName),
                "email": str(entry.mail or entry.userPrincipalName or ""),
                "department": str(entry.department or ""),
                "source": "ldap",
            }
            for entry in connection.entries
        ]
    finally:
        connection.unbind()


def oidc_config() -> Dict[str, str]:
    return {
        "name": os.getenv("OIDC_PROVIDER_NAME", "Keycloak"),
        "discovery_url": os.getenv("OIDC_DISCOVERY_URL", ""),
        "client_id": os.getenv("OIDC_CLIENT_ID", ""),
        "client_secret": os.getenv("OIDC_CLIENT_SECRET", ""),
        "scope": os.getenv("OIDC_SCOPE", "openid email profile"),
    }
