"""Database models.

Importing this package registers every model with SQLAlchemy's metadata.
"""

from .audit import AuditEvent, record_event
from .firm import Firm
from .matter import Matter, MatterType
from .types import UTCDateTime, utcnow
from .user import ROLE_ADMIN, ROLE_MEMBER, User

__all__ = [
    "AuditEvent",
    "Firm",
    "Matter",
    "MatterType",
    "ROLE_ADMIN",
    "ROLE_MEMBER",
    "UTCDateTime",
    "User",
    "record_event",
    "utcnow",
]
