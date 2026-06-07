"""
Cloud connectors service (Google Sheets, Airtable, Notion).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pandas as pd


class GoogleSheetsConnector:
    """Google Sheets connector using Google API."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.api_key = config.get("api_key")
        self.spreadsheet_id = config.get("spreadsheet_id")
        self.sheet_name = config.get("sheet_name", "Sheet1")

    def pull_data(self) -> List[Dict[str, Any]]:
        """Pull data from Google Sheets."""
        try:
            import requests

            url = f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}/values/{self.sheet_name}"
            params = {"key": self.api_key}
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            values = data.get("values", [])
            if not values:
                return []
            headers = values[0]
            rows = []
            for row in values[1:]:
                rows.append(
                    {
                        headers[i]: row[i] if i < len(row) else ""
                        for i in range(len(headers))
                    }
                )
            return rows
        except Exception as e:
            raise Exception(f"Google Sheets pull failed: {str(e)}")

    def push_data(self, rows: List[Dict[str, Any]]) -> None:
        """Push data to Google Sheets."""
        try:
            import requests

            if not rows:
                return
            headers = list(rows[0].keys())
            values = [headers] + [[row.get(h, "") for h in headers] for row in rows]
            url = f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}/values/{self.sheet_name}:clear"
            requests.post(
                url,
                params={"key": self.api_key},
                json={},
                timeout=10,
            )
            url = f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}/values/{self.sheet_name}:append"
            requests.post(
                url,
                params={"key": self.api_key, "valueInputOption": "RAW"},
                json={"values": values},
                timeout=10,
            )
        except Exception as e:
            raise Exception(f"Google Sheets push failed: {str(e)}")


class AirtableConnector:
    """Airtable connector using Airtable API."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.api_key = config.get("api_key")
        self.base_id = config.get("base_id")
        self.table_name = config.get("table_name")

    def pull_data(self) -> List[Dict[str, Any]]:
        """Pull data from Airtable."""
        try:
            import requests

            url = f"https://api.airtable.com/v0/{self.base_id}/{self.table_name}"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            records = data.get("records", [])
            return [r.get("fields", {}) for r in records]
        except Exception as e:
            raise Exception(f"Airtable pull failed: {str(e)}")

    def push_data(self, rows: List[Dict[str, Any]]) -> None:
        """Push data to Airtable."""
        try:
            import requests

            url = f"https://api.airtable.com/v0/{self.base_id}/{self.table_name}"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            for row in rows:
                requests.post(url, headers=headers, json={"fields": row}, timeout=10)
        except Exception as e:
            raise Exception(f"Airtable push failed: {str(e)}")


class NotionConnector:
    """Notion connector using Notion API."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.api_key = config.get("api_key")
        self.database_id = config.get("database_id")

    def pull_data(self) -> List[Dict[str, Any]]:
        """Pull data from Notion database."""
        try:
            import requests

            url = f"https://api.notion.com/v1/databases/{self.database_id}/query"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            }
            resp = requests.post(url, headers=headers, json={}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            rows = []
            for result in results:
                props = result.get("properties", {})
                row = {}
                for key, value in props.items():
                    if value.get("type") == "title" and value.get("title"):
                        row[key] = value["title"][0].get("plain_text", "")
                    elif value.get("type") == "rich_text" and value.get("rich_text"):
                        row[key] = value["rich_text"][0].get("plain_text", "")
                    elif value.get("type") == "number":
                        row[key] = value.get("number")
                    elif value.get("type") == "select":
                        row[key] = value.get("select", {}).get("name", "")
                rows.append(row)
            return rows
        except Exception as e:
            raise Exception(f"Notion pull failed: {str(e)}")

    def push_data(self, rows: List[Dict[str, Any]]) -> None:
        """Push data to Notion (simplified - would need proper property mapping)."""
        # Implementation would require mapping to Notion property types
        pass


def get_connector(connector_type: str, config: Dict[str, Any]):
    """Factory function to get connector instance."""
    if connector_type == "google_sheets":
        return GoogleSheetsConnector(config)
    elif connector_type == "airtable":
        return AirtableConnector(config)
    elif connector_type == "notion":
        return NotionConnector(config)
    else:
        raise ValueError(f"Unknown connector type: {connector_type}")
