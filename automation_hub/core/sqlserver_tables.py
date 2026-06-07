"""
SQL Server storage for promoted user tables.

We store the grid JSON (columns + rows) as NVARCHAR(MAX) so we don't need to
create dynamic SQL tables per user.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator, Optional


def get_sqlserver_conn_str() -> str:
    """
    Provide a full ODBC connection string via env, e.g.:
    TABLES_SQLSERVER_CONN_STR="DRIVER={ODBC Driver 18 for SQL Server};SERVER=...;DATABASE=...;UID=...;PWD=...;TrustServerCertificate=yes;"
    """
    return (os.getenv("TABLES_SQLSERVER_CONN_STR") or "").strip()


def is_enabled() -> bool:
    return bool(get_sqlserver_conn_str())


@contextmanager
def connect() -> Iterator[Any]:
    conn_str = get_sqlserver_conn_str()
    if not conn_str:
        raise RuntimeError("TABLES_SQLSERVER_CONN_STR is not set")
    try:
        import pyodbc  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("pyodbc is not installed") from e

    conn = pyodbc.connect(conn_str, timeout=10)
    try:
        yield conn
    finally:
        conn.close()


def init_schema() -> None:
    """Create SQL Server tables for promoted storage."""
    if not is_enabled():
        return
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
            IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[user_tables]') AND type in (N'U'))
            BEGIN
                CREATE TABLE [dbo].[user_tables](
                    [table_id] NVARCHAR(256) NOT NULL PRIMARY KEY,
                    [owner_username] NVARCHAR(256) NOT NULL,
                    [title] NVARCHAR(256) NOT NULL,
                    [content_json] NVARCHAR(MAX) NOT NULL,
                    [updated_at] DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
                    [promoted_at] DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
                );
            END
            """)
        conn.commit()


def upsert_table(
    table_id: str,
    owner_username: str,
    title: str,
    content_json: str,
) -> None:
    with connect() as conn:
        cur = conn.cursor()
        # MERGE for upsert
        cur.execute(
            """
            MERGE [dbo].[user_tables] AS target
            USING (SELECT ? AS table_id) AS src
            ON target.table_id = src.table_id
            WHEN MATCHED THEN
                UPDATE SET owner_username = ?, title = ?, content_json = ?, updated_at = SYSUTCDATETIME()
            WHEN NOT MATCHED THEN
                INSERT (table_id, owner_username, title, content_json)
                VALUES (?, ?, ?, ?);
            """,
            (
                table_id,
                owner_username,
                title,
                content_json,
                table_id,
                owner_username,
                title,
                content_json,
            ),
        )
        conn.commit()


def get_table_content_json(table_id: str) -> Optional[str]:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT content_json FROM [dbo].[user_tables] WHERE table_id = ?",
            (table_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return row[0]
