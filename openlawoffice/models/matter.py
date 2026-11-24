"""Matter and matter type models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .types import UTCDateTime, utcnow
from .user import User


class MatterType(db.Model):
    __tablename__ = "matter_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_name: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_id])

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<MatterType {self.name}>"


class Matter(db.Model):
    __tablename__ = "matters"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    matter_type_id: Mapped[int] = mapped_column(
        ForeignKey("matter_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    jurisdiction: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    matter_type: Mapped[MatterType] = relationship(lazy="joined")
    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_id])

    @property
    def short_description(self) -> str:
        if not self.description:
            return ""
        compact = " ".join(self.description.split())
        return compact if len(compact) <= 140 else compact[:137] + "..."

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Matter {self.title}>"
