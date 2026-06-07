"""Audit log: write actions to DB."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from . import db as _db


def audit_log(
    username: Optional[str],
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    try:
        conn = _db.db_connect(_db.get_db_file())
        try:
            conn.execute(
                "INSERT INTO audit_log(at,username,action,target_type,target_id,details_json) VALUES (?,?,?,?,?,?)",
                (
                    _db.utc_now_iso(),
                    username or "",
                    action,
                    target_type or "",
                    target_id or "",
                    json.dumps(details) if details else None,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print(f"Audit log failed: {e}")
