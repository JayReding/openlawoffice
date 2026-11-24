"""Shared Flask extension instances and the SQLAlchemy declarative base."""

from __future__ import annotations

import sqlite3

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base shared by every model."""


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()

login_manager.login_view = "auth.login"
login_manager.login_message = "Please sign in to continue."
login_manager.login_message_category = "info"
login_manager.session_protection = "strong"


@login_manager.user_loader
def load_user(user_id: str):
    # Imported lazily to avoid an import cycle during app creation.
    from .models import User

    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


@event.listens_for(Engine, "connect")
def enforce_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """SQLite ignores foreign keys unless they are enabled per connection."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
