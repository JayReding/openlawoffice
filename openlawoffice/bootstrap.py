"""First-run detection and schema bootstrapping.

The application is considered initialized once at least one user exists. Until
then every non-asset route redirects to the one-time setup screen.
"""

from __future__ import annotations

from pathlib import Path

from flask import current_app, g
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from .extensions import db
from .models import User


def _sqlite_database_path() -> Path | None:
    """Resolve the on-disk SQLite file, if the app is using one."""
    try:
        url = make_url(current_app.config["SQLALCHEMY_DATABASE_URI"])
    except Exception:  # pragma: no cover - reported when the engine is used
        return None
    if url.get_backend_name() != "sqlite" or not url.database:
        return None
    if url.database == ":memory:" or url.database.startswith("file:"):
        return None
    path = Path(url.database)
    if not path.is_absolute():
        # Flask-SQLAlchemy resolves relative SQLite paths against instance/.
        path = Path(current_app.instance_path) / path
    return path


def ensure_schema() -> None:
    """Create any missing tables.

    This makes the first run work out of the box. Once the project begins
    evolving its schema, use Flask-Migrate/Alembic for versioned migrations.
    """
    db.create_all()

    # Tighten permissions on the database file that SQLite may have just
    # created. Server databases handle access control themselves.
    sqlite_path = _sqlite_database_path()
    if sqlite_path is not None and sqlite_path.exists():
        try:
            sqlite_path.chmod(0o600)
        except OSError:  # pragma: no cover - platform/filesystem dependent
            current_app.logger.warning(
                "Could not restrict permissions on %s", sqlite_path
            )


def is_initialized() -> bool:
    """Return True when the database is reachable and contains a user."""
    if "olo_initialized" in g:
        return g.olo_initialized

    initialized = False
    try:
        initialized = db.session.scalar(select(User.id).limit(1)) is not None
    except SQLAlchemyError as exc:
        db.session.rollback()
        initialized = False
        # A missing schema on a fresh install is expected. Anything else is
        # worth surfacing to operators.
        underlying = str(getattr(exc, "orig", exc)).lower()
        missing_schema = (
            "no such table" in underlying
            or "does not exist" in underlying
            or "doesn't exist" in underlying
        )
        if missing_schema:
            current_app.logger.debug("Schema is not initialized yet.")
        else:
            current_app.logger.warning(
                "Database is unavailable while checking initialization state.",
                exc_info=True,
            )

    g.olo_initialized = initialized
    return initialized


def mark_initialized() -> None:
    g.olo_initialized = True


def database_label() -> str:
    """A credential-free description of the configured database backend."""
    try:
        backend = make_url(
            current_app.config["SQLALCHEMY_DATABASE_URI"]
        ).get_backend_name()
    except Exception:  # pragma: no cover - malformed URL is reported elsewhere
        return "database"
    return {
        "sqlite": "SQLite",
        "postgresql": "PostgreSQL",
        "postgres": "PostgreSQL",
        "mysql": "MariaDB / MySQL",
        "mariadb": "MariaDB / MySQL",
    }.get(backend, backend)
