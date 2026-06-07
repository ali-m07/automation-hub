"""
Postgres helper for the Data Tables feature.

This app uses SQLite for most internal features, but we can store user-created tables
in Postgres by setting POSTGRES_DSN (or DATABASE_URL).
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional


def get_postgres_dsn() -> str:
    return (os.getenv("POSTGRES_DSN") or os.getenv("DATABASE_URL") or "").strip()


def is_enabled() -> bool:
    return bool(get_postgres_dsn())


@contextmanager
def pg_connect() -> Iterator[Any]:
    """
    Context-managed psycopg connection.
    Import is inside function so the app can still run without psycopg installed.
    """
    dsn = get_postgres_dsn()
    if not dsn:
        raise RuntimeError("POSTGRES_DSN (or DATABASE_URL) is not set")
    try:
        import psycopg  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("psycopg is not installed") from e

    conn = psycopg.connect(dsn)
    try:
        yield conn
    finally:
        conn.close()


def init_tables_schema() -> None:
    """
    Create required tables for Data Grid storage in Postgres.
    Safe to call multiple times.
    """
    if not is_enabled():
        return

    with pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tables_meta (
                    table_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    owner_username TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_opened_at TIMESTAMPTZ NULL,
                    storage_backend TEXT NOT NULL DEFAULT 'postgres',
                    promoted_sqlserver_conn_id INTEGER NULL,
                    promote_status TEXT NOT NULL DEFAULT 'draft'
                )
                """)
            # If this DB existed before storage_backend fields were added
            cur.execute("""
                ALTER TABLE tables_meta
                ADD COLUMN IF NOT EXISTS storage_backend TEXT NOT NULL DEFAULT 'postgres'
                """)
            cur.execute("""
                ALTER TABLE tables_meta
                ADD COLUMN IF NOT EXISTS promoted_sqlserver_conn_id INTEGER NULL
                """)
            cur.execute("""
                ALTER TABLE tables_meta
                ADD COLUMN IF NOT EXISTS promote_status TEXT NOT NULL DEFAULT 'draft'
                """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS table_grants (
                    table_id TEXT NOT NULL,
                    grantee_username TEXT NOT NULL,
                    permission TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (table_id, grantee_username)
                )
                """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS share_tokens (
                    token TEXT PRIMARY KEY,
                    table_id TEXT NOT NULL,
                    expires_at TIMESTAMPTZ NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS table_favorites (
                    username TEXT NOT NULL,
                    table_id TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (username, table_id)
                )
                """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tables_data (
                    table_id TEXT PRIMARY KEY,
                    content JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS table_versions (
                    id BIGSERIAL PRIMARY KEY,
                    table_id TEXT NOT NULL,
                    version_number INTEGER NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    content JSONB
                )
                """)
            # Column validation rules per table/column (JSON schema-like)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS table_column_rules (
                    id BIGSERIAL PRIMARY KEY,
                    table_id TEXT NOT NULL,
                    column_name TEXT NOT NULL,
                    rule_json JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (table_id, column_name)
                )
                """)
        conn.commit()


def row_to_dict(row, columns) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return {columns[i]: row[i] for i in range(len(columns))}
