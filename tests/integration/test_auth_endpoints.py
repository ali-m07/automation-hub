"""Integration tests for authentication endpoints."""

import pytest
from fastapi.testclient import TestClient


class TestLoginEndpoint:
    """Test login endpoint."""

    def test_login_page_get(self, client: TestClient):
        """Test GET /login returns login page."""
        response = client.get("/login")
        assert response.status_code == 200
        assert "login" in response.text.lower()

    def test_login_success(self, client: TestClient):
        """Test successful login."""
        # First, create a user
        from automation_hub.core.db import init_database, db_connect, get_db_file
        from automation_hub.core.auth import hash_password

        init_database()
        conn = db_connect(get_db_file())
        try:
            conn.execute(
                "INSERT OR REPLACE INTO users (username, password, role, level, status) VALUES (?, ?, ?, ?, ?)",
                (
                    "test@example.com",
                    hash_password("Test123!"),
                    "user",
                    "ops",
                    "active",
                ),
            )
            conn.commit()
        finally:
            conn.close()

        # Try to login
        response = client.post(
            "/login",
            data={"username": "test@example.com", "password": "Test123!"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers.get("location") in ("/", "/summary")

    def test_login_invalid_credentials(self, client: TestClient):
        """Test login with invalid credentials."""
        response = client.post(
            "/login",
            data={"username": "nonexistent@example.com", "password": "WrongPass123!"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "login" in response.headers.get("location", "").lower()

    def test_login_requires_authentication(self, client: TestClient):
        """Test that protected pages require authentication."""
        response = client.get("/summary", follow_redirects=False)
        assert response.status_code == 302
        assert "login" in response.headers.get("location", "").lower()


class TestLogoutEndpoint:
    """Test logout endpoint."""

    def test_logout(self, authenticated_client: TestClient):
        """Test logout clears session."""
        response = authenticated_client.get("/logout", follow_redirects=False)
        assert response.status_code == 302
        assert "login" in response.headers.get("location", "").lower()

        # Should not be able to access protected pages after logout
        response = authenticated_client.get("/summary", follow_redirects=False)
        assert response.status_code == 302


class TestProfileEndpoints:
    """Test profile endpoints."""

    def test_get_profile(self, authenticated_client: TestClient):
        """Test GET /api/me returns user profile."""
        response = authenticated_client.get("/api/me")
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is True
        assert "user" in data
        assert data["user"]["username"] == "admin@test.com"
        assert data["user"]["role"] == "admin"

    def test_update_profile(self, authenticated_client: TestClient):
        """Test POST /api/me/update updates user profile."""
        response = authenticated_client.post(
            "/api/me/update",
            json={
                "first_name": "Test",
                "last_name": "User",
                "email": "admin@test.com",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
