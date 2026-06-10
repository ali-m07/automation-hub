"""Enterprise authentication configuration and provisioning tests."""

from automation_hub.core import db
from automation_hub.services import enterprise_auth


def test_provider_flags_require_configuration(monkeypatch):
    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.delenv("OIDC_DISCOVERY_URL", raising=False)
    monkeypatch.setenv("LDAP_ENABLED", "true")
    monkeypatch.delenv("LDAP_SERVER", raising=False)

    assert enterprise_auth.oidc_enabled() is False
    assert enterprise_auth.ldap_enabled() is False


def test_provision_external_user_with_feedback_access(test_settings, monkeypatch):
    monkeypatch.setenv("SSO_DEFAULT_MODULES", "feedback_180")
    db.init_database()

    user = enterprise_auth.provision_user(
        "Person@Example.com",
        "oidc",
        "subject-123",
        "Test",
        "Person",
    )

    assert user["username"] == "person@example.com"
    assert user["status"] == "active"
    assert user["auth_provider"] == "oidc"
    assert enterprise_auth.auth.user_modules_from_record(user) == ["feedback_180"]
