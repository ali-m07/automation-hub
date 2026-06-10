"""Active Directory/LDAP and OIDC user provisioning."""

from __future__ import annotations

import json
import os
import secrets
from typing import Any, Dict, Optional

from automation_hub.core import auth, db


def enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def oidc_enabled() -> bool:
    return enabled("OIDC_ENABLED") and bool(os.getenv("OIDC_DISCOVERY_URL"))


def ldap_enabled() -> bool:
    return enabled("LDAP_ENABLED") and bool(os.getenv("LDAP_SERVER"))


def _default_modules() -> list[str]:
    raw = os.getenv("SSO_DEFAULT_MODULES", "feedback")
    return [item.strip() for item in raw.split(",") if item.strip()]


def provision_user(
    username: str,
    provider: str,
    subject: str = "",
    first_name: str = "",
    last_name: str = "",
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
                    first_name, last_name, created_at, auth_provider, external_subject
                ) VALUES (?, ?, 'user', 'user', ?, ?, 'active', ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    auth.hash_password(secrets.token_urlsafe(32)),
                    json.dumps(_default_modules()),
                    username,
                    first_name,
                    last_name,
                    now,
                    provider,
                    subject,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE users SET auth_provider = ?, external_subject = ?,
                    first_name = COALESCE(NULLIF(?, ''), first_name),
                    last_name = COALESCE(NULLIF(?, ''), last_name)
                WHERE username = ?
                """,
                (provider, subject, first_name, last_name, username),
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
        os.environ["LDAP_SERVER"],
        port=int(os.getenv("LDAP_PORT", "636")),
        use_ssl=enabled("LDAP_USE_SSL"),
        get_info=ALL,
        connect_timeout=10,
    )
    user_principal = os.getenv("LDAP_USER_PRINCIPAL", "{username}").format(
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
        base_dn = os.getenv("LDAP_BASE_DN", "")
        search_filter = os.getenv(
            "LDAP_USER_FILTER", "(sAMAccountName={username})"
        ).format(username=username.replace("\\", "").replace("*", ""))
        connection.search(
            base_dn,
            search_filter,
            search_scope=SUBTREE,
            attributes=["mail", "userPrincipalName", "givenName", "sn", "objectGUID"],
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
        )
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
