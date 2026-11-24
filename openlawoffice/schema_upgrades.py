"""Additive schema upgrades for databases created before a field existed.

The application still uses ``db.create_all()`` for new tables. SQLAlchemy does
not add columns to existing tables, so this module applies the small set of
additive user-profile changes required by the user-management feature and
backfills usernames for existing accounts.

Replace this with Alembic/Flask-Migrate before making destructive or complex
schema changes.
"""

from __future__ import annotations

import re

from flask import current_app
from sqlalchemy import inspect, or_, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .extensions import db
from .models import PROFESSIONAL_ROLE_DEFAULT, User
from .validation import normalize_username

USER_COLUMN_DDL = {
    "username": "VARCHAR(50)",
    "telephone": "VARCHAR(32)",
    "office": "VARCHAR(100)",
    "professional_role": (
        f"VARCHAR(40) NOT NULL DEFAULT '{PROFESSIONAL_ROLE_DEFAULT}'"
    ),
    "department": "VARCHAR(100)",
}


def _column_names(engine: Engine) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns("users")}


def _add_missing_columns(engine: Engine) -> None:
    existing = _column_names(engine)
    for name, ddl in USER_COLUMN_DDL.items():
        if name in existing:
            continue
        try:
            with engine.begin() as connection:
                connection.execute(text(f"ALTER TABLE users ADD COLUMN {name} {ddl}"))
        except SQLAlchemyError:
            # Another worker may have added it between our check and ALTER.
            if name not in _column_names(engine):
                raise
            current_app.logger.debug("User column %s was added concurrently.", name)


def _username_seed(user: User) -> str:
    source = ""
    if user.email:
        source = user.email.split("@", 1)[0]
    if not source and user.full_name:
        source = user.full_name

    candidate = re.sub(r"[^a-z0-9._-]", "", normalize_username(source)).strip("._-")
    if not candidate or not candidate[0].isalnum():
        candidate = f"user{user.id}"
    if len(candidate) < 3:
        candidate = f"{candidate}user{user.id}"
    return candidate[:44] or f"user{user.id}"


def _unique_username(base: str, used: set[str]) -> str:
    candidate = base[:50]
    counter = 2
    while candidate in used:
        suffix = f"-{counter}"
        candidate = f"{base[: 50 - len(suffix)]}{suffix}"
        counter += 1
    return candidate


def _backfill_usernames() -> None:
    missing = db.session.scalars(
        select(User).where(or_(User.username.is_(None), User.username == ""))
    ).all()
    if not missing:
        return

    used = {
        username for username in db.session.scalars(select(User.username)) if username
    }
    for user in missing:
        username = _unique_username(_username_seed(user), used)
        user.username = username
        used.add(username)

    try:
        db.session.commit()
    except IntegrityError:  # pragma: no cover - concurrent startup race
        db.session.rollback()
        current_app.logger.warning(
            "Could not backfill every legacy username. Administrators can "
            "edit usernames from the user management page."
        )


def _ensure_professional_role_default() -> None:
    with db.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE users SET professional_role = :role "
                "WHERE professional_role IS NULL OR professional_role = ''"
            ),
            {"role": PROFESSIONAL_ROLE_DEFAULT},
        )


def _ensure_username_index(engine: Engine) -> None:
    inspector = inspect(engine)
    for index in inspector.get_indexes("users"):
        if index.get("unique") and index.get("column_names") == ["username"]:
            return
    for constraint in inspector.get_unique_constraints("users") or []:
        if constraint.get("column_names") == ["username"]:
            return

    try:
        with engine.begin() as connection:
            connection.execute(
                text("CREATE UNIQUE INDEX ix_users_username ON users (username)")
            )
    except SQLAlchemyError:  # pragma: no cover - concurrent startup race
        current_app.logger.warning(
            "Could not create the unique username index. Check for duplicate "
            "usernames before restarting.",
            exc_info=True,
        )


def upgrade_user_schema() -> None:
    """Add missing user profile columns and backfill legacy usernames."""
    engine = db.engine
    if not inspect(engine).has_table("users"):
        return

    _add_missing_columns(engine)
    _ensure_professional_role_default()
    _backfill_usernames()
    _ensure_username_index(engine)
