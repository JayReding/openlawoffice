"""Firm lookup helpers shared by views and templates."""

from __future__ import annotations

from flask import g
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from .extensions import db
from .models import AuditEvent, Firm

FIRM_CACHE_KEY = "olo_firm"
FIRM_UPDATED_ACTION = "firm.updated"


def get_firm() -> Firm | None:
    """Return the current firm, or None when it has not been configured yet.

    Failures are tolerated so the setup and database-error screens can still
    render when the database is unavailable.
    """
    if FIRM_CACHE_KEY in g:
        return g.get(FIRM_CACHE_KEY)

    firm = None
    try:
        firm = db.session.scalar(select(Firm).order_by(Firm.id).limit(1))
    except SQLAlchemyError:
        db.session.rollback()

    setattr(g, FIRM_CACHE_KEY, firm)
    return firm


def has_saved_firm_settings() -> bool:
    """Return True once an administrator has successfully changed firm settings.

    The audit log is the source of truth so merely opening the settings page,
    or submitting an unchanged form, does not complete the checklist item.
    """
    try:
        return (
            db.session.scalar(
                select(AuditEvent.id)
                .where(AuditEvent.action == FIRM_UPDATED_ACTION)
                .limit(1)
            )
            is not None
        )
    except SQLAlchemyError:
        db.session.rollback()
        return False


def cache_firm(firm: Firm | None) -> None:
    setattr(g, FIRM_CACHE_KEY, firm)
