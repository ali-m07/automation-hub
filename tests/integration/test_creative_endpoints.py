"""Integration tests for Creative (Photoshop/PSD) module endpoints."""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
from PIL import ImageFont


class TestCreativeEndpoints:
    """Test Creative Studio (PSD) endpoints."""

    def test_creative_page_requires_auth(self, client: TestClient):
        """GET /creative redirects to login when not authenticated."""
        response = client.get("/creative", follow_redirects=False)
        assert response.status_code == 302
        assert "login" in response.headers.get("location", "").lower()

    def test_creative_page_accessible_when_authenticated(
        self, authenticated_client: TestClient
    ):
        """GET /creative returns 200 when authenticated."""
        response = authenticated_client.get("/creative", follow_redirects=False)
        assert response.status_code == 200
        assert (
            "creative" in response.text.lower()
            or "photoshop" in response.text.lower()
            or "psd" in response.text.lower()
        )

    def test_upload_psd_endpoint_exists(self, authenticated_client: TestClient):
        """POST /api/upload-psd exists and returns JSON (e.g. 400 without file)."""
        response = authenticated_client.post("/api/upload-psd", follow_redirects=False)
        # Without file we expect 422 (validation) or 400
        assert response.status_code in (400, 422)
        data = response.json()
        assert "detail" in data or "error" in data or "success" in data

    def test_font_list_and_upload(
        self, authenticated_client: TestClient, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("FONT_DIR", str(tmp_path))
        font_path = Path(ImageFont.truetype("Arial.ttf", 16).path)

        upload = authenticated_client.post(
            "/api/creative/fonts",
            files={"file": ("Arial.ttf", font_path.read_bytes(), "font/ttf")},
        )
        assert upload.status_code == 201
        uploaded = upload.json()["font"]

        response = authenticated_client.get("/api/creative/fonts")
        assert response.status_code == 200
        assert any(font["id"] == uploaded["id"] for font in response.json()["fonts"])

    def test_font_upload_rejects_bad_content(
        self, authenticated_client: TestClient, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("FONT_DIR", str(tmp_path))

        response = authenticated_client.post(
            "/api/creative/fonts",
            files={"file": ("broken.ttf", b"not a font", "font/ttf")},
        )
        assert response.status_code == 400
