"""Pytest configuration and shared fixtures."""

import os
import sys
import tempfile
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("SESSION_SECRET", "test-only-session-secret")

from app import app  # noqa: E402
from automation_hub.core.config import reload_settings, get_settings  # noqa: E402


@pytest.fixture(scope="function")
def temp_db() -> Generator[Path, None, None]:
    """Create a temporary database file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


@pytest.fixture(scope="function")
def test_settings(monkeypatch, temp_db: Path) -> Generator[dict, None, None]:
    """Override settings for testing."""
    # Set test environment variables
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("SESSION_SECRET", "test-secret-key")
    monkeypatch.setenv("DB_FILE", str(temp_db))

    # Create temp directories
    temp_upload = tempfile.mkdtemp()
    temp_output = tempfile.mkdtemp()

    monkeypatch.setenv("UPLOAD_DIR", temp_upload)
    monkeypatch.setenv("OUTPUT_DIR", temp_output)

    # Reload settings
    reload_settings()

    yield get_settings()

    # Cleanup
    import shutil

    shutil.rmtree(temp_upload, ignore_errors=True)
    shutil.rmtree(temp_output, ignore_errors=True)


@pytest.fixture(scope="function")
def client(test_settings) -> Generator[TestClient, None, None]:
    """Create a test client for FastAPI app."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="function")
def authenticated_client(client: TestClient) -> Generator[TestClient, None, None]:
    """Create an authenticated test client (admin user)."""
    # Create admin user and login
    from automation_hub.core.db import init_database, db_connect, get_db_file
    from automation_hub.core.auth import hash_password

    init_database()
    conn = db_connect(get_db_file())
    try:
        # Ensure admin exists (users table: username, password, role, level; migrations add status, etc.)
        conn.execute(
            "INSERT OR REPLACE INTO users (username, password, role, level, status) VALUES (?, ?, ?, ?, ?)",
            (
                "admin@test.com",
                hash_password("Test-Only-Passphrase-42!"),
                "admin",
                "system",
                "active",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    # Login
    response = client.post(
        "/login",
        data={"username": "admin@test.com", "password": "Test-Only-Passphrase-42!"},
        follow_redirects=False,
    )
    assert response.status_code in (200, 302)

    yield client


@pytest.fixture(scope="function")
def sample_user_data() -> dict:
    """Sample user data for testing."""
    return {
        "username": "test@example.com",
        "password": "TestPassword123!",
        "role": "user",
        "status": "active",
    }
