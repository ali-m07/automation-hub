"""Unit tests for configuration module."""

import os
import tempfile
from pathlib import Path

import pytest
from automation_hub.core.config import Settings, get_settings, reload_settings


class TestSettings:
    """Test Settings class."""

    def test_default_values(self):
        """Test default settings values."""
        settings = Settings()
        assert settings.app_name == "Servexa"
        assert settings.app_version == "2.0.0"
        assert settings.debug is False
        assert settings.host == "0.0.0.0"
        assert settings.port == 8000
        assert settings.max_upload_mb == 100
        assert settings.max_files_per_request == 20

    def test_max_upload_bytes_property(self):
        """Test max_upload_bytes property."""
        settings = Settings(max_upload_mb=50)
        assert settings.max_upload_bytes == 50 * 1024 * 1024

    def test_is_development_property(self):
        """Test is_development property."""
        dev_settings = Settings(environment="development", debug=True)
        assert dev_settings.is_development is True

        prod_settings = Settings(environment="production", debug=False)
        assert prod_settings.is_development is False

    def test_is_production_property(self):
        """Test is_production property."""
        prod_settings = Settings(environment="production", debug=False)
        assert prod_settings.is_production is True

        dev_settings = Settings(environment="development", debug=True)
        assert dev_settings.is_production is False

    def test_enable_2fa_parsing(self):
        """Test ENABLE_2FA parsing."""
        assert Settings(enable_2fa="1").enable_2fa is True
        assert Settings(enable_2fa="true").enable_2fa is True
        assert Settings(enable_2fa="yes").enable_2fa is True
        assert Settings(enable_2fa="0").enable_2fa is False
        assert Settings(enable_2fa="false").enable_2fa is False
        assert Settings(enable_2fa=True).enable_2fa is True
        assert Settings(enable_2fa=False).enable_2fa is False

    def test_directory_creation(self):
        """Test that directories are created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            upload_dir = Path(tmpdir) / "test_uploads"
            settings = Settings(upload_dir=str(upload_dir))
            assert upload_dir.exists()
            assert upload_dir.is_dir()

    def test_upload_limits_validation(self):
        """Test upload limits validation."""
        # Valid values
        settings = Settings(max_upload_mb=50, max_files_per_request=10)
        assert settings.max_upload_mb == 50
        assert settings.max_files_per_request == 10

        # Boundary values
        settings = Settings(max_upload_mb=1, max_files_per_request=1)
        assert settings.max_upload_mb == 1
        assert settings.max_files_per_request == 1

        settings = Settings(max_upload_mb=10240, max_files_per_request=1000)
        assert settings.max_upload_mb == 10240
        assert settings.max_files_per_request == 1000


class TestSettingsSingleton:
    """Test settings singleton pattern."""

    def test_get_settings_singleton(self):
        """Test that get_settings returns singleton."""
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2

    def test_reload_settings(self):
        """Test reload_settings creates new instance."""
        original = get_settings()
        reloaded = reload_settings()
        assert reloaded is not original
        # Next call should return the reloaded instance
        assert get_settings() is reloaded


class TestEnvironmentVariables:
    """Test loading from environment variables."""

    def test_load_from_env(self, monkeypatch):
        """Test loading settings from environment variables."""
        monkeypatch.setenv("APP_NAME", "Test App")
        monkeypatch.setenv("DEBUG", "true")
        monkeypatch.setenv("PORT", "9000")
        monkeypatch.setenv("MAX_UPLOAD_MB", "200")

        reload_settings()
        settings = get_settings()

        assert settings.app_name == "Test App"
        assert settings.debug is True
        assert settings.port == 9000
        assert settings.max_upload_mb == 200
