"""Integration tests for health check endpoints."""

import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_health_endpoint(self, client: TestClient):
        """Test GET /health returns OK."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"

    def test_live_endpoint(self, client: TestClient):
        """Test GET /live returns OK (liveness probe)."""
        response = client.get("/live")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "alive"

    def test_ready_endpoint(self, client: TestClient):
        """Test GET /ready checks database connectivity."""
        response = client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ready"
