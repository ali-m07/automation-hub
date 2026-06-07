"""
External database connector service: SQL Server (pyodbc) connection and
Excel-to-table sync (staging + MERGE). Used by Automation Hub Data & Connectors.
Moved from top-level db_connector_service.py into automation_hub.services.
"""

import io
import logging
import os
import platform
import re
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Optional pyodbc – only used when connector feature is used
try:
    import pyodbc
except ImportError:
    pyodbc = None


def safe_remove(path: str, retries: int = 8, delay_seconds: float = 0.15) -> bool:
    """Best-effort file removal (handles Windows file lock). Returns True if removed or missing."""
    if not path:
        return True
    for attempt in range(retries):
        try:
            if not os.path.exists(path):
                return True
            os.remove(path)
            return True
        except (PermissionError, OSError) as e:
            if attempt == retries - 1:
                logger.warning("safe_remove failed for %s: %s", path, e)
                return False
            time.sleep(delay_seconds * (attempt + 1))
    return False


def get_odbc_driver() -> str:
    """Return first available SQL Server ODBC driver for this platform."""
    if not pyodbc:
        raise RuntimeError(
            "pyodbc is not installed. Install it to use database connectors."
        )
    system = platform.system()
    if system == "Windows":
        candidates = [
            "ODBC Driver 18 for SQL Server",
            "ODBC Driver 17 for SQL Server",
            "SQL Server Native Client 11.0",
            "SQL Server",
        ]
    else:
        candidates = ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server"]
    available = pyodbc.drivers()
    for driver in candidates:
        if driver in available:
            return driver
    raise RuntimeError("No SQL Server ODBC driver found. Available: %s" % (available,))


def build_connection_string(credentials: Dict[str, Any], driver: str) -> str:
    """Build ODBC connection string from credentials dict."""
    use_trusted = credentials.get("trusted_connection", False)
    if use_trusted:
        conn_str = (
            f"DRIVER={{{driver}}};"
            f"SERVER={credentials['server']};"
            f"DATABASE={credentials['database']};"
            "Trusted_Connection=yes;"
        )
    else:
        conn_str = (
            f"DRIVER={{{driver}}};"
            f"SERVER={credentials['server']};"
            f"DATABASE={credentials['database']};"
            f"UID={credentials['username']};"
            f"PWD={credentials['password']};"
        )
    if credentials.get("extra_params"):
        conn_str += ";" + credentials["extra_params"]
    # For internal networks with self-signed certs, default to trusting the server
    # unless Encrypt/TrustServerCertificate have been explicitly set.
    upper = conn_str.upper()
    if "ENCRYPT=" not in upper and "TRUSTSERVERCERTIFICATE=" not in upper:
        conn_str += ";Encrypt=yes;TrustServerCertificate=yes"
    return conn_str


@contextmanager
def get_sql_connection(conn_config: Dict[str, Any]):
    """Context manager: yield a pyodbc connection. conn_config has server, database, username, password, extra_params, optional trusted_connection."""
    if not pyodbc:
        raise RuntimeError("pyodbc is not installed.")
    driver = get_odbc_driver()
    conn_str = build_connection_string(conn_config, driver)
    conn = None
    try:
        conn = pyodbc.connect(conn_str, timeout=15)
        yield conn
    except pyodbc.Error as e:
        logger.error("Database connection failed: %s", e)
        raise
    finally:
        if conn:
            conn.close()


def sanitize_column_name(col_name: Any) -> str:
    """Sanitize column name for SQL (alphanumeric and underscore)."""
    if col_name is None or (isinstance(col_name, float) and pd.isna(col_name)):
        return "Unnamed_Column_0"
    s = str(col_name).strip()
    s = re.sub(r"[^a-zA-Z0-9_]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        return "col_%s" % (abs(hash(str(col_name))) % 100000,)
    return s


def _staging_table_name(raw_table: str) -> str:
    """Temp staging table name (e.g. #hr_operations_list_staging) to avoid DROP on target DB."""
    raw_clean = raw_table.replace("[", "").replace("]", "")
    last_part = raw_clean.split(".")[-1]
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", last_part)
    return "#" + safe + "_staging"


def _temp_object_id(staging_name: str) -> str:
    """Return tempdb object id for DROP check (e.g. tempdb..#mytable_staging)."""
    return "tempdb.." + staging_name


def sync_excel_to_connector(
    filepath: str,
    sheet_name: str,
    conn_config: Dict[str, Any],
    table_name: str,
    primary_key_columns: List[str],
    chunk_size: int = 500,
) -> bool:
    """
    Read Excel sheet, insert into staging table, MERGE into target table.
    table_name: fully qualified e.g. [db].[dbo].[TableName].
    primary_key_columns: list of column names (as in Excel/table).
    """
    if not pyodbc:
        raise RuntimeError("pyodbc is not installed.")
    try:
        with open(filepath, "rb") as f:
            file_bytes = f.read()
        df = pd.read_excel(
            io.BytesIO(file_bytes), sheet_name=sheet_name, engine="openpyxl"
        )
    except Exception as e:
        logger.error("Failed to read Excel %s sheet %s: %s", filepath, sheet_name, e)
        return False

    original_columns = df.columns.tolist()
    # Always use temp staging table (no DROP permission needed on target DB)
    staging_name = _staging_table_name(table_name)

    try:
        with get_sql_connection(conn_config) as conn:
            cursor = conn.cursor()

            # Drop and create temp staging (all columns NVARCHAR(MAX) for simplicity)
            cols_sql = ", ".join("[%s] NVARCHAR(MAX)" % c for c in original_columns)
            obj_id = _temp_object_id(staging_name)
            cursor.execute(
                "IF OBJECT_ID('%s', 'U') IS NOT NULL DROP TABLE %s;"
                % (obj_id, staging_name)
            )
            create_sql = "CREATE TABLE %s (%s);" % (staging_name, cols_sql)
            cursor.execute(create_sql)
            conn.commit()

            total_rows = len(df)
            for i in range(0, total_rows, chunk_size):
                chunk = df.iloc[i : i + chunk_size]
                chunk_str = chunk.astype(str)
                chunk_str = chunk_str.where(pd.notna(chunk_str), None).replace(
                    {"nan": None, "NaT": None, "None": None}
                )
                cols_sql = ", ".join("[%s]" % c for c in original_columns)
                placeholders = ", ".join(["?"] * len(original_columns))
                insert_sql = "INSERT INTO %s (%s) VALUES (%s)" % (
                    staging_name,
                    cols_sql,
                    placeholders,
                )
                rows = [tuple(r) for r in chunk_str.itertuples(index=False, name=None)]
                if rows:
                    cursor.fast_executemany = True
                    cursor.executemany(insert_sql, rows)
            conn.commit()

            if total_rows == 0:
                return True

            # MERGE: target table vs staging
            on_parts = []
            for pk in primary_key_columns:
                on_parts.append("target.[%s] = source.[%s]" % (pk, pk))
            on_clause = " AND ".join(on_parts)

            update_cols = [c for c in original_columns if c not in primary_key_columns]
            set_parts = ["target.[%s] = source.[%s]" % (c, c) for c in update_cols]
            update_set = ", ".join(set_parts)

            insert_cols = ", ".join("[%s]" % c for c in original_columns)
            source_cols = ", ".join("source.[%s]" % c for c in original_columns)

            merge_sql = (
                "MERGE INTO %s AS target "
                "USING %s AS source ON %s "
                "WHEN MATCHED THEN UPDATE SET %s "
                "WHEN NOT MATCHED BY TARGET THEN INSERT (%s) VALUES (%s);"
                % (
                    table_name,
                    staging_name,
                    on_clause,
                    update_set,
                    insert_cols,
                    source_cols,
                )
            )
            cursor.execute(merge_sql)
            conn.commit()
            logger.info(
                "Sync complete: %s rows processed into %s", total_rows, table_name
            )
            return True
    except Exception as e:
        logger.exception("Sync failed: %s", e)
        return False


def preview_table_rows(
    conn_config: Dict[str, Any],
    table_name: str,
    limit: int = 200,
) -> Dict[str, Any]:
    """
    Return a preview of rows from the target table.
    This is read-only and intended for UI overview (no edits).
    """
    if not pyodbc:
        raise RuntimeError("pyodbc is not installed.")
    # limit <= 0 means "no limit" (load all rows). Otherwise clamp to a very high max.
    try:
        limit = int(limit)
    except Exception:
        limit = 0
    if limit > 0 and limit > 10000:
        limit = 10000

    if limit and limit > 0:
        query = f"SELECT TOP {limit} * FROM {table_name}"
    else:
        query = f"SELECT * FROM {table_name}"

    with get_sql_connection(conn_config) as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall() or []
        cols = [c[0] for c in cursor.description] if cursor.description else []

    def _to_jsonable(value: Any) -> Any:
        if value is None:
            return None
        # Convert non-JSON-serializable types (e.g. Decimal, datetime) to string
        try:
            import datetime
            from decimal import Decimal
        except Exception:  # pragma: no cover
            datetime = None
            Decimal = None
        if "datetime" in str(type(value)).lower():
            return value.isoformat()
        if hasattr(value, "isoformat"):
            try:
                return value.isoformat()
            except Exception:
                return str(value)
        if "decimal" in str(type(value)).lower():
            try:
                return float(value)
            except Exception:
                return str(value)
        return value

    data_rows: List[Dict[str, Any]] = []
    for row in rows:
        as_list = list(row)
        data_rows.append({cols[i]: _to_jsonable(as_list[i]) for i in range(len(cols))})

    return {"columns": cols, "rows": data_rows}


def export_table_to_csv(
    conn_config: Dict[str, Any],
    table_name: str,
    filename: Optional[str] = None,
) -> Dict[str, Any]:
    """Export entire table to CSV (for download)."""
    if not pyodbc:
        raise RuntimeError("pyodbc is not installed.")

    if not filename:
        # Derive a simple filename from table name
        raw_clean = table_name.replace("[", "").replace("]", "")
        last_part = raw_clean.split(".")[-1] or "table"
        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", last_part)
        filename = f"{safe_name}.csv"

    with get_sql_connection(conn_config) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {table_name}")
        cols = [c[0] for c in cursor.description] if cursor.description else []

        import csv

        buf = io.StringIO()
        writer = csv.writer(buf)
        if cols:
            writer.writerow(cols)
        for row in cursor:
            writer.writerow(list(row))

    return {"filename": filename, "content": buf.getvalue()}
