"""SQL Server connection for Employee Roster (Chargoon)."""

import os
from typing import Any, Dict, List, Optional
from contextlib import contextmanager

# Database connection settings
SQL_SERVER_HOST = os.getenv("SQL_SERVER_HOST", "172.20.0.58")
SQL_SERVER_INSTANCE = os.getenv("SQL_SERVER_INSTANCE", "Employeeroaster")
SQL_SERVER_DATABASE = os.getenv("SQL_SERVER_DATABASE", "Chargoon_view")
SQL_SERVER_USERNAME = os.getenv("SQL_SERVER_USERNAME", "SRE")
SQL_SERVER_PASSWORD = os.getenv("SQL_SERVER_PASSWORD", "%f7n:#aE4?G,f.^]fiKD")


def get_connection_string() -> str:
    """Build the SQL Server connection string."""
    return (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={SQL_SERVER_HOST}\\{SQL_SERVER_INSTANCE};"
        f"DATABASE={SQL_SERVER_DATABASE};"
        f"UID={SQL_SERVER_USERNAME};"
        f"PWD={SQL_SERVER_PASSWORD};"
        f"TrustServerCertificate=yes;"
    )


@contextmanager
def get_connection():
    """Get a SQL Server connection context manager."""
    try:
        import pyodbc

        conn_str = get_connection_string()
        conn = pyodbc.connect(conn_str, timeout=30)
        try:
            yield conn
        finally:
            conn.close()
    except ImportError:
        raise ImportError(
            "pyodbc is required for SQL Server connection. Install with: pip install pyodbc"
        )
    except Exception as e:
        raise ConnectionError(f"Failed to connect to SQL Server: {e}")


def test_connection() -> bool:
    """Test the SQL Server connection."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            return True
    except Exception as e:
        print(f"SQL Server connection failed: {e}")
        return False


def search_employees(
    query: str = "",
    limit: int = 50,
    active_only: bool = True,
    team: str = "",
    sub_team: str = "",
    vertical: str = "",
) -> List[Dict[str, Any]]:
    """Search employees from the Chargoon roster by EMAIL ONLY.

    Args:
        query: Search query (searches only email)
        limit: Maximum number of results
        active_only: Only return active employees

    Returns:
        List of employee dictionaries
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            # Search ONLY by email
            sql = """
                SELECT
                    PersonnelNo,
                    Active,
                    FullName,
                    EFullName,
                    ESnappEmail,
                    Title,
                    [Top Manager Name] as TopManagerName,
                    [Line Manager Name] as LineManagerName,
                    [Main Department] as MainDepartment,
                    Team,
                    SubTeam,
                    Vertical,
                    SubVertical,
                    Line_Manager_Email,
                    Top_Manager_Email,
                    Line_Line_Manager,
                    Line_Line_Manager_Email
                FROM [Chargoon_View].[dbo].[SRE_Chart]
                WHERE 1=1
            """

            params = []

            if query and len(query.strip()) >= 1:
                sql += " AND ESnappEmail LIKE ?"
                pattern = f"%{query.strip().lower()}%"
                params.append(pattern)
            if team:
                sql += " AND Team = ?"
                params.append(team)
            if sub_team:
                sql += " AND SubTeam = ?"
                params.append(sub_team)
            if vertical:
                sql += " AND Vertical = ?"
                params.append(vertical)

            sql += f" ORDER BY ESnappEmail OFFSET 0 ROWS FETCH NEXT {limit} ROWS ONLY"

            cursor.execute(sql, params)
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchall()

            employees = []
            for row in rows:
                emp = dict(zip(columns, row))
                # Filter active in Python to avoid type conversion issues
                if active_only and emp.get("Active") not in (
                    1,
                    "1",
                    "Active",
                    "active",
                    True,
                ):
                    continue
                employees.append(
                    {
                        "username": (
                            emp.get("ESnappEmail", "").split("@")[0]
                            if emp.get("ESnappEmail")
                            else ""
                        ),
                        "personnel_no": emp.get("PersonnelNo", ""),
                        "full_name": emp.get("FullName", ""),
                        "e_full_name": emp.get("EFullName", ""),
                        "email": emp.get("ESnappEmail", ""),
                        "job_title": emp.get("Title", ""),
                        "team": emp.get("Team", "") or emp.get("SubTeam", ""),
                        "sub_team": emp.get("SubTeam", ""),
                        "vertical": emp.get("Vertical", ""),
                        "sub_vertical": emp.get("SubVertical", ""),
                        "main_department": emp.get("MainDepartment", ""),
                        "line_manager_name": emp.get("LineManagerName", ""),
                        "line_manager_email": emp.get("Line_Manager_Email", ""),
                        "top_manager_name": emp.get("TopManagerName", ""),
                        "top_manager_email": emp.get("Top_Manager_Email", ""),
                        "line_line_manager": emp.get("Line_Line_Manager", ""),
                        "line_line_manager_email": emp.get(
                            "Line_Line_Manager_Email", ""
                        ),
                        "active": bool(emp.get("Active", False)),
                    }
                )

            return employees

    except Exception as e:
        print(f"Error searching employees: {e}")
        return []


def get_employee_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Get a single employee by email address."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            sql = """
                SELECT
                    PersonnelNo,
                    Active,
                    FullName,
                    EFullName,
                    ESnappEmail,
                    Title,
                    [Top Manager Name] as TopManagerName,
                    [Line Manager Name] as LineManagerName,
                    [Main Department] as MainDepartment,
                    Team,
                    SubTeam,
                    Vertical,
                    SubVertical,
                    Line_Manager_Email,
                    Top_Manager_Email,
                    Line_Line_Manager,
                    Line_Line_Manager_Email
                FROM [Chargoon_View].[dbo].[SRE_Chart]
                WHERE ESnappEmail = ?
            """

            cursor.execute(sql, (email,))
            row = cursor.fetchone()

            if not row:
                return None

            columns = [column[0] for column in cursor.description]
            emp = dict(zip(columns, row))

            return {
                "username": (
                    emp.get("ESnappEmail", "").split("@")[0]
                    if emp.get("ESnappEmail")
                    else ""
                ),
                "personnel_no": emp.get("PersonnelNo", ""),
                "full_name": emp.get("FullName", ""),
                "e_full_name": emp.get("EFullName", ""),
                "email": emp.get("ESnappEmail", ""),
                "job_title": emp.get("Title", ""),
                "team": emp.get("Team", "") or emp.get("SubTeam", ""),
                "sub_team": emp.get("SubTeam", ""),
                "vertical": emp.get("Vertical", ""),
                "sub_vertical": emp.get("SubVertical", ""),
                "main_department": emp.get("MainDepartment", ""),
                "line_manager_name": emp.get("LineManagerName", ""),
                "line_manager_email": emp.get("Line_Manager_Email", ""),
                "top_manager_name": emp.get("TopManagerName", ""),
                "top_manager_email": emp.get("Top_Manager_Email", ""),
                "line_line_manager": emp.get("Line_Line_Manager", ""),
                "line_line_manager_email": emp.get("Line_Line_Manager_Email", ""),
                "active": bool(emp.get("Active", False)),
            }

    except Exception as e:
        print(f"Error getting employee by email: {e}")
        return None


def get_employee_manager_chain(email: str) -> List[Dict[str, Any]]:
    """Get the management chain for an employee."""
    employee = get_employee_by_email(email)
    if not employee:
        return []

    chain = [employee]

    # Get line manager
    if employee.get("line_manager_email"):
        manager = get_employee_by_email(employee["line_manager_email"])
        if manager:
            chain.append(manager)

            # Get top manager
            if manager.get("line_manager_email"):
                top_manager = get_employee_by_email(manager["line_manager_email"])
                if top_manager:
                    chain.append(top_manager)

    return chain


def get_all_teams() -> List[str]:
    """Get list of all teams."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT Team
                FROM [Chargoon_View].[dbo].[SRE_Chart]
                WHERE Active = 1 AND Team IS NOT NULL AND Team != ''
                ORDER BY Team
            """)
            return [row[0] for row in cursor.fetchall()]
    except Exception as e:
        print(f"Error getting teams: {e}")
        return []


def get_all_verticals() -> List[str]:
    """Get list of all verticals."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT Vertical
                FROM [Chargoon_View].[dbo].[SRE_Chart]
                WHERE Active = 1 AND Vertical IS NOT NULL AND Vertical != ''
                ORDER BY Vertical
            """)
            return [row[0] for row in cursor.fetchall()]
    except Exception as e:
        print(f"Error getting verticals: {e}")
        return []


def get_all_sub_teams() -> List[str]:
    """Get list of all active sub-teams."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT SubTeam
                FROM [Chargoon_View].[dbo].[SRE_Chart]
                WHERE Active = 1 AND SubTeam IS NOT NULL AND SubTeam != ''
                ORDER BY SubTeam
            """)
            return [row[0] for row in cursor.fetchall()]
    except Exception as e:
        print(f"Error getting sub-teams: {e}")
        return []
