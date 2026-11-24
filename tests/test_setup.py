"""First-run setup behavior."""

from __future__ import annotations

import re

from sqlalchemy import select

from openlawoffice.extensions import db
from openlawoffice.models import AuditEvent, User

from .conftest import ADMIN_EMAIL, ADMIN_NAME, ADMIN_PASSWORD, create_admin, make_app


def test_uninitialized_app_redirects_to_setup(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/setup" in response.headers["Location"]

    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "/setup" in response.headers["Location"]


def test_setup_screen_is_available(client):
    response = client.get("/setup")
    assert response.status_code == 200
    assert b"Set up your account" in response.data
    assert b"Create administrator" in response.data
    assert b"disabled" not in response.data


def test_health_check_reports_uninitialized_without_redirect(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["database"] == "ok"
    assert payload["initialized"] is False


def test_setup_creates_admin_and_signs_in(app, client):
    response = create_admin(client, follow_redirects=True)
    assert response.status_code == 200
    assert b"Good to see you" in response.data
    assert b"Administrator" in response.data

    with app.app_context():
        user = db.session.scalar(select(User))
        assert user is not None
        assert user.email == ADMIN_EMAIL
        assert user.full_name == ADMIN_NAME
        assert user.role == "admin"
        assert user.active is True
        assert user.last_login_at is not None
        assert user.password_hash != ADMIN_PASSWORD
        assert ADMIN_PASSWORD not in user.password_hash
        assert user.check_password(ADMIN_PASSWORD)

        event = db.session.scalar(
            select(AuditEvent).where(AuditEvent.action == "setup.completed")
        )
        assert event is not None
        assert event.actor_id == user.id


def test_setup_is_locked_after_completion(client):
    create_admin(client)
    client.post("/logout")

    response = client.get("/setup")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

    response = client.post(
        "/setup",
        data={
            "full_name": "Second Admin",
            "email": "second@example.com",
            "password": "Second-Administrator-42",
            "confirm_password": "Second-Administrator-42",
        },
    )
    assert response.status_code == 302


def test_weak_password_is_rejected(app, client):
    response = client.post(
        "/setup",
        data={
            "full_name": ADMIN_NAME,
            "email": ADMIN_EMAIL,
            "password": "short",
            "confirm_password": "short",
        },
    )
    assert response.status_code == 200
    assert b"at least 12 characters" in response.data

    with app.app_context():
        assert db.session.scalar(select(User.id)) is None


def test_password_mismatch_is_rejected(app, client):
    response = client.post(
        "/setup",
        data={
            "full_name": ADMIN_NAME,
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
            "confirm_password": ADMIN_PASSWORD + "-different",
        },
    )
    assert response.status_code == 200
    assert b"Passwords must match" in response.data

    with app.app_context():
        assert db.session.scalar(select(User.id)) is None


def test_setup_does_not_store_password_in_audit_detail(app, client):
    create_admin(client)
    with app.app_context():
        event = db.session.scalar(
            select(AuditEvent).where(AuditEvent.action == "setup.completed")
        )
        assert event.detail == {"email": ADMIN_EMAIL}
        assert ADMIN_PASSWORD not in str(event.detail)


def test_setup_token_is_enforced(tmp_path):
    app = make_app(tmp_path, SETUP_TOKEN="one-time-office-token")
    client = app.test_client()

    response = client.post(
        "/setup",
        data={
            "full_name": ADMIN_NAME,
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
            "confirm_password": ADMIN_PASSWORD,
            "setup_token": "wrong-token",
        },
    )
    assert response.status_code == 200
    assert b"Incorrect setup token" in response.data

    with app.app_context():
        assert db.session.scalar(select(User.id)) is None
        db.session.remove()
        db.drop_all()

    response = client.post(
        "/setup",
        data={
            "full_name": ADMIN_NAME,
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
            "confirm_password": ADMIN_PASSWORD,
            "setup_token": "one-time-office-token",
        },
    )
    assert response.status_code == 302


def test_csrf_is_required_for_setup(tmp_path):
    app = make_app(tmp_path, WTF_CSRF_ENABLED=True)
    client = app.test_client()

    response = client.post(
        "/setup",
        data={
            "full_name": ADMIN_NAME,
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
            "confirm_password": ADMIN_PASSWORD,
        },
    )
    assert response.status_code == 400
    assert b"security token was invalid" in response.data

    page = client.get("/setup")
    match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', page.data)
    assert match is not None

    response = client.post(
        "/setup",
        data={
            "csrf_token": match.group(1).decode(),
            "full_name": ADMIN_NAME,
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
            "confirm_password": ADMIN_PASSWORD,
        },
    )
    assert response.status_code == 302

    with app.app_context():
        assert db.session.scalar(select(User.id)) is not None


def test_security_headers_are_present(client):
    response = client.get("/setup")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["Cache-Control"] == "no-store"
