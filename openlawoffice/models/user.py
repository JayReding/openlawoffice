"""User account model."""

from __future__ import annotations

from datetime import datetime

from flask_login import UserMixin
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from .types import UTCDateTime, utcnow

ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default=ROLE_MEMBER, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    failed_login_count: Mapped[int] = mapped_column(default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    @property
    def is_active(self) -> bool:  # Flask-Login uses this to reject sign-ins.
        return self.active

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)
        self.password_changed_at = utcnow()

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.email} ({self.role})>"
