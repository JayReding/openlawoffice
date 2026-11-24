"""Contact records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .types import UTCDateTime, utcnow
from .user import User


class Contact(db.Model):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    organization: Mapped[str | None] = mapped_column(String(200), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(150), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mobile: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address_line_1: Mapped[str | None] = mapped_column(String(150), nullable=True)
    address_line_2: Mapped[str | None] = mapped_column(String(150), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_id])

    @property
    def full_name(self) -> str:
        return " ".join(
            part for part in (self.first_name, self.last_name) if part
        ).strip()

    @property
    def display_name(self) -> str:
        return self.full_name or self.organization or self.email or "Unnamed contact"

    @property
    def source_label(self) -> str:
        return {
            "manual": "Manual",
            "vcard": "vCard",
            "csv": "CSV",
            "ics": "Calendar",
        }.get(self.source, self.source.title())

    @property
    def city_state_postal(self) -> str:
        locality = ", ".join(part for part in (self.city, self.state) if part)
        if self.postal_code:
            return f"{locality} {self.postal_code}".strip()
        return locality

    @property
    def address_lines(self) -> list[str]:
        lines = [line for line in (self.address_line_1, self.address_line_2) if line]
        if self.city_state_postal:
            lines.append(self.city_state_postal)
        if self.country:
            lines.append(self.country)
        return lines

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Contact {self.display_name}>"
