"""Append-only security and account audit events."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import has_request_context, request
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db
from .types import UTCDateTime, utcnow


class AuditEvent(db.Model):
    """A minimal audit trail for authentication and administrative actions.

    Legal practice software benefits from a durable record of who did what and
    when. Events are intentionally simple for now and can be expanded as
    matter, time, and billing features are added.
    """

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, index=True, nullable=False
    )


def record_event(
    action: str,
    *,
    actor=None,
    detail: dict[str, Any] | None = None,
) -> AuditEvent:
    """Stage an audit event on the current session. The caller commits."""
    ip_address = None
    user_agent = None
    if has_request_context():
        ip_address = request.remote_addr
        user_agent = request.user_agent.string or None

    event = AuditEvent(
        action=action,
        actor_id=getattr(actor, "id", None),
        ip_address=ip_address,
        user_agent=user_agent[:512] if user_agent else None,
        detail=detail,
    )
    db.session.add(event)
    return event
