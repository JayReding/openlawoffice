"""Database models.

Importing this package registers every model with SQLAlchemy's metadata.
"""

from .audit import AuditEvent, record_event
from .contact import Contact
from .firm import Firm
from .matter import Matter, MatterType
from .types import UTCDateTime, utcnow
from .user import (
    PROFESSIONAL_ROLE_DEFAULT,
    PROFESSIONAL_ROLES,
    ROLE_ADMIN,
    ROLE_MEMBER,
    User,
)

__all__ = [
    "AuditEvent",
    "Contact",
    "Firm",
    "Matter",
    "MatterType",
    "PROFESSIONAL_ROLE_DEFAULT",
    "PROFESSIONAL_ROLES",
    "ROLE_ADMIN",
    "ROLE_MEMBER",
    "UTCDateTime",
    "User",
    "record_event",
    "utcnow",
]
