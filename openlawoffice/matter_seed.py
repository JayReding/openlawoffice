"""Default matter types and idempotent seeding."""

from __future__ import annotations

from flask import current_app
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models import MatterType

DEFAULT_MATTER_TYPES = (
    "Appellate",
    "Bankruptcy",
    "Business Formation",
    "Business Litigation",
    "Civil",
    "Corporate",
    "Consumer Protection",
    "Criminal",
    "Debtor/Creditor",
    "Education",
    "Elder Law",
    "Employment",
    "ERISA",
    "Estate Planning",
    "Family Law",
    "General Litigation",
    "General Practice",
    "Government and Elections",
    "Guardianship",
    "Immigration",
    "Insurance",
    "Intellectual Property",
    "Long-Term Care",
    "Military",
    "Minerals, Oil, and Gas",
    "Personal Injury",
    "Probate",
    "Real Estate",
    "Real Estate Litigation",
    "Social Security",
    "Tax",
    "Unemployment",
    "Workers Compensation",
)


def normalize_matter_type_name(value: str) -> str:
    """Normalize a type name for uniqueness while preserving display input."""
    return " ".join((value or "").split()).casefold()


def display_matter_type_name(value: str) -> str:
    return " ".join((value or "").split())


def seed_default_matter_types() -> int:
    """Insert any missing default types. Returns the number inserted.

    Safe to run repeatedly and safe across concurrent application processes:
    the unique normalized name constraint prevents duplicates, and a failed
    insert is retried once after re-reading the existing names.
    """
    for _attempt in range(2):
        try:
            existing = set(db.session.scalars(select(MatterType.normalized_name)))
            inserted = 0
            for name in DEFAULT_MATTER_TYPES:
                normalized = normalize_matter_type_name(name)
                if normalized in existing:
                    continue
                db.session.add(
                    MatterType(
                        name=name,
                        normalized_name=normalized,
                        is_default=True,
                        active=True,
                    )
                )
                existing.add(normalized)
                inserted += 1
            db.session.commit()
            return inserted
        except IntegrityError:
            db.session.rollback()

    current_app.logger.warning("Could not seed all default matter types.")
    return 0
