"""Application configuration using Pydantic Settings."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="Automation Hub", description="Application name")
    app_version: str = Field(default="2.0.0", description="Application version")
    debug: bool = Field(default=False, description="Debug mode")
    environment: str = Field(
        default="production", description="Environment (development/production)"
    )

    # Server
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")

    # Security
    session_secret: str = Field(
        default="",
        description="Session secret key (use strong random value in production)",
    )
    enable_2fa: bool = Field(
        default=False,
        description="Enable 2FA enforcement (set to 1/true/yes to enable)",
    )

    # Database
    db_file: Optional[str] = Field(
        default=None,
        description="SQLite database file path (default: app.db in current directory)",
    )
    app_data_dir: Optional[str] = Field(
        default=None,
        description="Application data directory (for DB and data_pools)",
    )

    # Upload limits
    max_upload_mb: int = Field(
        default=100,
        ge=1,
        le=10240,
        description="Maximum upload size in MB",
    )
    max_files_per_request: int = Field(
        default=20,
        ge=1,
        le=1000,
        description="Maximum files per upload request",
    )

    # SMTP / Email
    smtp_server: Optional[str] = Field(
        default=None,
        description="SMTP server hostname",
    )
    smtp_port: int = Field(default=587, ge=1, le=65535, description="SMTP server port")
    smtp_user: Optional[str] = Field(default=None, description="SMTP username")
    smtp_password: Optional[str] = Field(default=None, description="SMTP password")
    admin_email: Optional[str] = Field(
        default=None,
        description="Admin email for notifications",
    )

    # Redis (optional)
    redis_url: Optional[str] = Field(
        default=None,
        description="Redis connection URL (e.g., redis://localhost:6379/0)",
    )

    # Directories
    upload_dir: Path = Field(default=Path("uploads"), description="Upload directory")
    output_dir: Path = Field(default=Path("outputs"), description="Output directory")
    gallery_dir: Path = Field(default=Path("gallery"), description="Gallery directory")
    templates_psd_dir: Path = Field(
        default=Path("templates_psd"),
        description="PSD templates directory",
    )
    font_dir: Path = Field(
        default=Path("fonts"), description="Application font directory"
    )

    @field_validator("enable_2fa", mode="before")
    @classmethod
    def parse_enable_2fa(cls, v: str | bool) -> bool:
        """Parse ENABLE_2FA from string to bool."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("1", "true", "yes", "on")
        return False

    @field_validator(
        "upload_dir",
        "output_dir",
        "gallery_dir",
        "templates_psd_dir",
        "font_dir",
        mode="before",
    )
    @classmethod
    def create_directories(cls, v: str | Path) -> Path:
        """Ensure directories exist."""
        path = Path(v) if isinstance(v, str) else v
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def max_upload_bytes(self) -> int:
        """Get maximum upload size in bytes."""
        return self.max_upload_mb * 1024 * 1024

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment.lower() == "development" or self.debug

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment.lower() == "production" and not self.debug


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get global settings instance (singleton pattern)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Reload settings from environment (useful for testing)."""
    global _settings
    _settings = Settings()
    return _settings
