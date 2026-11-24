"""Shared field normalization and validation helpers."""

from __future__ import annotations

import re

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,49}$")
USERNAME_HELP = (
    "Use 3-50 lowercase letters, numbers, dots, underscores, or hyphens, "
    "starting with a letter or number."
)


def normalize_username(value: str | None) -> str:
    return (value or "").strip().lower()


def username_error(value: str) -> str | None:
    if not value:
        return "Enter a username."
    if not USERNAME_RE.fullmatch(value):
        return USERNAME_HELP
    return None


def normalize_us_phone(value: str) -> str:
    """Return a formatted 10-digit U.S. phone number or raise ValueError."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        raise ValueError("Enter a 10-digit U.S. telephone number.")
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


def normalize_postal_code(value: str) -> str:
    """Return ZIP or ZIP+4 normalization or raise ValueError."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 5:
        return digits
    if len(digits) == 9:
        return f"{digits[:5]}-{digits[5:]}"
    raise ValueError("Enter a 5-digit ZIP code or ZIP+4.")
