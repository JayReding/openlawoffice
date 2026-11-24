"""Firm-wide profile and branding information."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db
from .types import UTCDateTime, utcnow


class Firm(db.Model):
    """The firm using this installation.

    Only one firm is used in the current single-firm model, but the table has a
    normal primary key so a future multi-firm version can add firm membership
    without removing a singleton constraint.
    """

    __tablename__ = "firms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    address_line_1: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address_line_2: Mapped[str | None] = mapped_column(String(120), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    telephone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)

    logo_stored_name: Mapped[str | None] = mapped_column(
        String(80), unique=True, nullable=True
    )
    logo_content_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    logo_size_bytes: Mapped[int | None] = mapped_column(nullable=True)
    logo_width: Mapped[int | None] = mapped_column(nullable=True)
    logo_height: Mapped[int | None] = mapped_column(nullable=True)
    logo_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    logo_uploaded_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, nullable=True
    )

    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    @property
    def has_logo(self) -> bool:
        return bool(self.logo_stored_name and self.logo_content_type)

    @property
    def city_state_zip(self) -> str:
        parts = [self.city, " ".join(filter(None, (self.state, self.postal_code)))]
        return ", ".join(part for part in parts if part)

    @property
    def address_lines(self) -> list[str]:
        """Formatted address lines for display or future invoice templates."""
        lines = [line for line in (self.address_line_1, self.address_line_2) if line]
        if self.city_state_zip:
            lines.append(self.city_state_zip)
        return lines

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Firm {self.name}>"
