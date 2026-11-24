"""Reusable column types and mixins."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """Store timestamps as UTC and always read them back as timezone-aware.

    SQLite has no native timezone support, so values are normalized on the way
    in and re-tagged as UTC on the way out. This keeps application code free of
    naive/aware comparison bugs across SQLite, PostgreSQL, and MariaDB.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
