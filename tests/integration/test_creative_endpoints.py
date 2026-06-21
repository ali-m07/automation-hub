"""Integration tests for Creative (Photoshop/PSD) module endpoints."""

import json
import pytest
from pathlib import Path
from urllib.parse import urlparse

from fastapi.testclient import TestClient
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

    def test_photopea_editor_session_roundtrip(
        self, authenticated_client: TestClient, monkeypatch, tmp_path
    ):
        from automation_hub.routers import creative as creative_module

        monkeypatch.setattr(creative_module, "UPLOAD_DIR", tmp_path)
        source_file = tmp_path / "template_demo.psd"
        source_file.write_bytes(b"original-psd")

        session_response = authenticated_client.post(
            "/api/creative/editor-session",
            data={"psd_file_id": source_file.name},
        )
        assert session_response.status_code == 200
        session_data = session_response.json()
        assert session_data["success"] is True
        assert "photopea.com#" in session_data["editor_url"]

        source_path = urlparse(session_data["source_url"]).path
        source_response = authenticated_client.get(source_path)
        assert source_response.status_code == 200
        assert source_response.content == b"original-psd"

        saved_psd = b"updated-psd"
        saved_png = b"preview-png"
        header = json.dumps(
            {
                "source": session_data["source_url"],
                "versions": [
                    {"format": "psd:true", "start": 0, "size": len(saved_psd)},
                    {
                        "format": "png",
                        "start": len(saved_psd),
                        "size": len(saved_png),
                    },
                ],
            }
        ).encode("utf-8")
        body = header.ljust(2000, b" ") + saved_psd + saved_png

        save_path = urlparse(session_data["save_url"]).path
        save_response = authenticated_client.post(
            save_path,
            content=body,
            headers={"Origin": "https://www.photopea.com"},
        )
        assert save_response.status_code == 200
        assert source_file.read_bytes() == saved_psd
        assert source_file.with_suffix(".photopea-preview.png").read_bytes() == saved_png

        status_response = authenticated_client.get(
            f"/api/creative/editor-session/{session_data['session_token']}"
        )
        assert status_response.status_code == 200
        status_data = status_response.json()["session"]
        assert status_data["last_saved_at"]
        assert "psd" in status_data["last_saved_formats"]
