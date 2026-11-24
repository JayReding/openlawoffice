"""Password policy, login lockout, and redirect safety helpers."""

from __future__ import annotations

import hmac
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from .models.types import utcnow

# A small deny-list catches the most common choices without shipping a large
# word list. Length remains the primary requirement (NIST SP 800-63B).
COMMON_PASSWORDS = frozenset(
    {
        "123456789012",
        "administrator",
        "changeme12345",
        "correcthorsebatterystaple",
        "iloveyou1234",
        "letmein12345",
        "openlawoffice",
        "password1234",
        "passwordpassword",
        "qwertyuiop123",
        "welcome12345",
    }
)

# Used to keep failed-login timing similar whether or not the account exists.
_DUMMY_HASH = generate_password_hash("open-law-office-timing-equalizer")


def normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def password_policy_errors(
    password: str,
    *,
    email: str = "",
    full_name: str = "",
    min_length: int | None = None,
    max_length: int | None = None,
) -> list[str]:
    """Return human-readable policy violations for a proposed password."""
    min_length = min_length or current_app.config["PASSWORD_MIN_LENGTH"]
    max_length = max_length or current_app.config["PASSWORD_MAX_LENGTH"]
    errors: list[str] = []

    if len(password) < min_length:
        errors.append(f"Use at least {min_length} characters.")
    if len(password) > max_length:
        errors.append(f"Use no more than {max_length} characters.")
    if password.strip() != password:
        errors.append("Do not start or end the password with spaces.")
    if password.casefold() in COMMON_PASSWORDS:
        errors.append("That password is too common. Choose something unique.")

    local_part = normalize_email(email).split("@", 1)[0]
    if len(local_part) >= 4 and local_part in password.casefold():
        errors.append("Do not include your email address in the password.")

    def alphanumeric(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", value.casefold())

    compact_name = alphanumeric(full_name)
    compact_password = alphanumeric(password)
    name_parts = [
        alphanumeric(part) for part in full_name.split() if len(alphanumeric(part)) >= 3
    ]
    if (len(compact_name) >= 6 and compact_name in compact_password) or any(
        part in compact_password for part in name_parts
    ):
        errors.append("Do not include your name in the password.")

    return errors


def check_password_or_dummy(user, password: str) -> bool:
    """Verify a password while burning comparable time for unknown accounts."""
    if user is None:
        check_password_hash(_DUMMY_HASH, password)
        return False
    return user.check_password(password)


def is_locked(user, now: datetime | None = None) -> bool:
    now = now or utcnow()
    return bool(user.locked_until and user.locked_until > now)


def register_failed_login(
    user,
    *,
    max_attempts: int | None = None,
    lockout_minutes: int | None = None,
) -> bool:
    """Record a failed attempt and lock the account if the limit is reached.

    Returns ``True`` when this attempt caused a lockout.
    """
    max_attempts = max_attempts or current_app.config["LOGIN_MAX_ATTEMPTS"]
    lockout_minutes = lockout_minutes or current_app.config["LOGIN_LOCKOUT_MINUTES"]
    now = utcnow()

    # An expired lock starts a fresh count.
    if user.locked_until and user.locked_until <= now:
        user.locked_until = None
        user.failed_login_count = 0

    user.failed_login_count = (user.failed_login_count or 0) + 1
    if user.failed_login_count >= max_attempts:
        user.failed_login_count = 0
        user.locked_until = now + timedelta(minutes=lockout_minutes)
        return True
    return False


def clear_failed_logins(user) -> None:
    user.failed_login_count = 0
    user.locked_until = None


def is_safe_redirect(target: str | None) -> bool:
    """Only allow same-site, path-absolute redirect targets."""
    if not target or not target.startswith("/") or target.startswith("//"):
        return False
    if "\\" in target or any(ord(char) < 32 or ord(char) == 127 for char in target):
        return False
    parsed = urlparse(target)
    return not parsed.scheme and not parsed.netloc


def secure_compare(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
