"""Shared constants (e.g. product modules list)."""

from __future__ import annotations

from typing import Any, Dict, List

# Product modules controlled by admin in /admin; stored per-user in SQLite as JSON list (users.modules_json)
MODULES: List[Dict[str, Any]] = [
    {
        "key": "data_tables_manual",
        "label": "Data: Manual table entry (Data & Connectors)",
    },
    {
        "key": "data_excel_to_sql",
        "label": "Data: Excel upload to SQL (import/connector)",
    },
    {"key": "creative_psd", "label": "Creative Studio (PSD processing)"},
    {"key": "messaging_send", "label": "Messaging (send emails)"},
    {"key": "connectors_db", "label": "Database Connectors (Excel sync to SQL Server)"},
    {"key": "feedback_180", "label": "180 Feedback: participant access"},
    {"key": "feedback_180_admin", "label": "180 Feedback: workflow and cycle admin"},
]
