"""Unit tests for authentication module."""

import pytest
from automation_hub.core import auth


class TestPasswordHashing:
    """Test password hashing functions."""

    def test_hash_password(self):
        """Test password hashing."""
        password = "TestPassword123!"
        hashed = auth.hash_password(password)
        assert hashed != password
        assert len(hashed) > 0
        assert hashed.startswith("$pbkdf2-sha256$")

    def test_verify_password(self):
        """Test password verification."""
        password = "TestPassword123!"
        hashed = auth.hash_password(password)
        assert auth.verify_password(password, hashed) is True
        assert auth.verify_password("wrong", hashed) is False

    def test_hash_password_deterministic(self):
        """Test that hashing same password produces different hashes (salt)."""
        password = "TestPassword123!"
        hash1 = auth.hash_password(password)
        hash2 = auth.hash_password(password)
        # Should be different due to salt
        assert hash1 != hash2
        # But both should verify correctly
        assert auth.verify_password(password, hash1) is True
        assert auth.verify_password(password, hash2) is True


class TestPasswordValidation:
    """Test password validation functions."""

    def test_validate_password_strength_valid(self):
        """Test valid passwords."""
        valid_passwords = [
            "TestPassword123!",
            "MyP@ssw0rdLong",
            "Str0ng!PassWord",
            "VeryLongPassword123!@#",
        ]
        for pwd in valid_passwords:
            result = auth.validate_password_strength(pwd)
            assert result is None, f"Password '{pwd}' should be valid but got: {result}"

    def test_validate_password_strength_too_short(self):
        """Test passwords that are too short."""
        result = auth.validate_password_strength("Short1!")
        assert result is not None
        assert "12" in result.lower() or "length" in result.lower()

    def test_validate_password_strength_no_uppercase(self):
        """Test passwords without uppercase."""
        result = auth.validate_password_strength("lowercase123!")
        assert result is not None
        assert "uppercase" in result.lower() or "capital" in result.lower()

    def test_validate_password_strength_no_lowercase(self):
        """Test passwords without lowercase."""
        result = auth.validate_password_strength("UPPERCASE123!")
        assert result is not None
        assert "lowercase" in result.lower()

    def test_validate_password_strength_no_digit(self):
        """Test passwords without digits."""
        result = auth.validate_password_strength("NoDigitsHere!")
        assert result is not None
        assert "digit" in result.lower() or "number" in result.lower()

    def test_validate_password_strength_no_special(self):
        """Test passwords without special characters."""
        result = auth.validate_password_strength("NoSpecial123")
        assert result is not None
        assert "special" in result.lower() or "symbol" in result.lower()


class TestEmailValidation:
    """Test email/username validation."""

    def test_validate_email_username_valid(self):
        """Test valid email addresses."""
        valid_emails = [
            "test@example.com",
            "user.name@domain.co.uk",
            "admin@localhost.local",
            "user+tag@example.org",
        ]
        for email in valid_emails:
            result = auth.validate_email_username(email)
            assert result is None, f"Email '{email}' should be valid but got: {result}"

    def test_validate_email_username_invalid(self):
        """Test invalid email addresses."""
        invalid_emails = [
            "notanemail",
            "@example.com",
            "user@",
            "user@domain",
            "user name@example.com",
        ]
        for email in invalid_emails:
            result = auth.validate_email_username(email)
            assert result is not None, f"Email '{email}' should be invalid"


class TestUserModules:
    """Test user module functions."""

    def test_user_has_module_admin(self):
        """Test that admin has all modules."""
        admin_user = {"role": "admin", "modules": []}
        assert auth.user_has_module(admin_user, "any_module") is True

    def test_user_has_module_with_access(self):
        """Test user with module access."""
        user = {"role": "user", "modules": ["creative", "messaging"]}
        assert auth.user_has_module(user, "creative") is True
        assert auth.user_has_module(user, "messaging") is True
        assert auth.user_has_module(user, "data") is False

    def test_user_has_module_no_user(self):
        """Test with no user."""
        assert auth.user_has_module(None, "any_module") is False
        assert auth.user_has_module({}, "any_module") is False
