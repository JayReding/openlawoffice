"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from openlawoffice import create_app
from openlawoffice.extensions import db

ADMIN_EMAIL = "admin@example.com"
ADMIN_NAME = "Ada Attorney"
ADMIN_USERNAME = "ada"
ADMIN_PASSWORD = "Willow-Meadow-Cobalt-42"


def make_app(tmp_path, **overrides):
    config = {
        "TESTING": True,
        "SECRET_KEY": "test-secret-key-that-is-long-enough",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
        "WTF_CSRF_ENABLED": False,
        "SETUP_TOKEN": None,
        "PASSWORD_MIN_LENGTH": 12,
        "LOGIN_MAX_ATTEMPTS": 3,
        "LOGIN_LOCKOUT_MINUTES": 15,
        "TIMEZONE": "America/New_York",
        "FIRM_LOGO_UPLOAD_DIR": str(tmp_path / "uploads" / "firm"),
    }
    config.update(overrides)
    return create_app(config)


@pytest.fixture()
def app(tmp_path):
    application = make_app(tmp_path)
    with application.app_context():
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def setup_payload():
    return {
        "username": ADMIN_USERNAME,
        "full_name": ADMIN_NAME,
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD,
        "confirm_password": ADMIN_PASSWORD,
    }


def create_admin(client, payload=None, *, follow_redirects=False, **extra):
    data = payload or {
        "username": ADMIN_USERNAME,
        "full_name": ADMIN_NAME,
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD,
        "confirm_password": ADMIN_PASSWORD,
    }
    return client.post(
        "/setup",
        data={**data, **extra},
        follow_redirects=follow_redirects,
    )
