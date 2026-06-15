"""Shared constants (e.g. product modules list)."""

from __future__ import annotations

from typing import Any, Dict, List

# Product modules controlled by admin in /admin; stored per-user in SQLite as JSON list (users.modules_json)
MODULES: List[Dict[str, Any]] = [
    {
        "key": "data_tables_manual",
        "label": "Data: Manual table entry (Data & Connectors)",
        "project": "Data & Connectors",
        "access_type": "user",
    },
    {
        "key": "data_excel_to_sql",
        "label": "Data: Excel upload to SQL (import/connector)",
        "project": "Data & Connectors",
        "access_type": "user",
    },
    {
        "key": "creative_psd",
        "label": "Creative Studio (PSD processing)",
        "project": "Creative",
        "access_type": "user",
    },
    {
        "key": "messaging_send",
        "label": "Messaging (send emails)",
        "project": "Messaging",
        "access_type": "user",
    },
    {
        "key": "connectors_db",
        "label": "Database Connectors (Excel sync to SQL Server)",
        "project": "Data & Connectors",
        "access_type": "user",
    },
    {
        "key": "ticketing",
        "label": "Helpdesk: portal and personal tickets",
        "project": "Helpdesk",
        "access_type": "user",
    },
    {
        "key": "ticketing_admin",
        "label": "Helpdesk: project administration",
        "project": "Helpdesk",
        "access_type": "admin",
    },
    {
        "key": "feedback_180",
        "label": "180 Feedback: participant access",
        "project": "Feedback",
        "access_type": "user",
    },
    {
        "key": "feedback_180_admin",
        "label": "180 Feedback: workflow and cycle admin",
        "project": "Feedback",
        "access_type": "admin",
    },
    {
        "key": "process_designer",
        "label": "Process Designer: use shared workflows and fields",
        "project": "Process Designer",
        "access_type": "user",
    },
    {
        "key": "process_designer_admin",
        "label": "Process Designer: manage shared workflows and fields",
        "project": "Process Designer",
        "access_type": "admin",
    },
]
