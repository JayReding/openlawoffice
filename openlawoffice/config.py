"""Configuration defaults and database URL helpers.

Configuration precedence (lowest to highest):

1. Values derived from environment variables by :func:`default_config`.
2. An optional ``instance/config.py`` file.
3. An explicit mapping passed to :func:`openlawoffice.create_app` (used by tests).
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

TRUE_VALUES = {"1", "true", "t", "yes", "y", "on"}


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in TRUE_VALUES


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def engine_options(database_url: str) -> dict:
    """Return engine options appropriate for the configured backend.

    SQLite gets a busy timeout so concurrent writers wait instead of failing
    immediately. Server databases use pre-ping and recycling to survive
    dropped connections.
    """
    options: dict = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"timeout": 30}
    else:
        options["pool_recycle"] = 1800
    return options


def default_config(instance_path: str) -> dict:
    environment = os.environ.get("APP_ENV", "development").strip().lower()
    is_production = environment == "production"

    database_url = os.environ.get("DATABASE_URL", "").strip()
    # Heroku-style URLs use a scheme SQLAlchemy no longer accepts.
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://") :]
    if not database_url:
        database_url = f"sqlite:///{Path(instance_path) / 'openlawoffice.db'}"

    trusted_hosts = [
        host.strip()
        for host in os.environ.get("TRUSTED_HOSTS", "").split(",")
        if host.strip()
    ]

    config = {
        "APP_NAME": "Open Law Office",
        "ENVIRONMENT": environment,
        "SECRET_KEY": os.environ.get("SECRET_KEY") or None,
        "SQLALCHEMY_DATABASE_URI": database_url,
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "SQLALCHEMY_ENGINE_OPTIONS": engine_options(database_url),
        # Session cookies.
        "SESSION_COOKIE_NAME": "olo_session",
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": env_bool("SESSION_COOKIE_SECURE", is_production),
        "REMEMBER_COOKIE_NAME": "olo_remember",
        "REMEMBER_COOKIE_HTTPONLY": True,
        "REMEMBER_COOKIE_SAMESITE": "Lax",
        "REMEMBER_COOKIE_SECURE": env_bool("REMEMBER_COOKIE_SECURE", is_production),
        "PERMANENT_SESSION_LIFETIME": timedelta(
            hours=env_int("SESSION_LIFETIME_HOURS", 12)
        ),
        "REMEMBER_COOKIE_DURATION": timedelta(days=30),
        "MAX_CONTENT_LENGTH": 4 * 1024 * 1024,
        # Firm logo storage and validation.
        "FIRM_LOGO_UPLOAD_DIR": os.environ.get("FIRM_LOGO_UPLOAD_DIR")
        or str(Path(instance_path) / "uploads" / "firm"),
        "FIRM_LOGO_MAX_BYTES": 2 * 1024 * 1024,
        "FIRM_LOGO_MAX_DIMENSION": 1600,
        "FIRM_LOGO_MIN_DIMENSION": 64,
        "FIRM_LOGO_MAX_PIXELS": 25_000_000,
        # Form security.
        "WTF_CSRF_TIME_LIMIT": 3600,
        "WTF_CSRF_SSL_STRICT": True,
        # Authentication policy.
        "PASSWORD_MIN_LENGTH": env_int("PASSWORD_MIN_LENGTH", 12),
        "PASSWORD_MAX_LENGTH": 128,
        "LOGIN_MAX_ATTEMPTS": env_int("LOGIN_MAX_ATTEMPTS", 5),
        "LOGIN_LOCKOUT_MINUTES": env_int("LOGIN_LOCKOUT_MINUTES", 15),
        "SETUP_TOKEN": os.environ.get("SETUP_TOKEN") or None,
        "TIMEZONE": os.environ.get("TIMEZONE", "America/New_York"),
        # Number of trusted reverse proxies in front of the app. Keep at 0
        # unless a proxy you control sets X-Forwarded-* headers.
        "TRUST_PROXY_HOPS": env_int("TRUST_PROXY_HOPS", 0),
    }
    if trusted_hosts:
        config["TRUSTED_HOSTS"] = trusted_hosts
    return config
