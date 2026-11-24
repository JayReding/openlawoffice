"""Unit tests for security helpers."""

from __future__ import annotations

from openlawoffice.security import (
    is_safe_redirect,
    normalize_email,
    password_policy_errors,
)


def test_normalize_email():
    assert normalize_email("  Admin@Example.COM ") == "admin@example.com"
    assert normalize_email(None) == ""


def test_safe_redirect_rules():
    assert is_safe_redirect("/dashboard")
    assert is_safe_redirect("/dashboard?tab=time")
    assert not is_safe_redirect(None)
    assert not is_safe_redirect("")
    assert not is_safe_redirect("https://evil.example.com")
    assert not is_safe_redirect("//evil.example.com")
    assert not is_safe_redirect("/\\evil.example.com")
    assert not is_safe_redirect("/dashboard\r\nLocation: https://evil.example.com")
    assert not is_safe_redirect("dashboard")
    assert not is_safe_redirect("javascript:alert(1)")


def test_password_policy(app):
    assert password_policy_errors("short") == [
        "Use at least 12 characters.",
    ]
    assert any(
        "too common" in error for error in password_policy_errors("passwordpassword")
    )
    assert any(
        "email address" in error
        for error in password_policy_errors(
            "admin-is-my-password", email="admin@example.com"
        )
    )
    assert any(
        "your name" in error
        for error in password_policy_errors(
            "adas-long-password", full_name="Ada Attorney"
        )
    )
    assert (
        password_policy_errors(
            "Willow-Meadow-Cobalt-42",
            email="admin@example.com",
            full_name="Ada Attorney",
        )
        == []
    )
