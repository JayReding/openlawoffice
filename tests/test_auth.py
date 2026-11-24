"""Authentication and account lockout behavior."""

from __future__ import annotations

from sqlalchemy import select

from openlawoffice.extensions import db
from openlawoffice.models import AuditEvent, User

from .conftest import ADMIN_EMAIL, ADMIN_PASSWORD, create_admin


def sign_out(client):
    return client.post("/logout")


def test_login_success_and_logout(app, client):
    create_admin(client)
    sign_out(client)

    response = client.post(
        "/login",
        data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Good to see you" in response.data
    assert b"Signed in as" in response.data

    with app.app_context():
        user = db.session.scalar(select(User))
        assert user.last_login_at is not None

    response = sign_out(client)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_email_is_case_insensitive(app, client):
    create_admin(client)
    sign_out(client)

    response = client.post(
        "/login",
        data={"email": "ADMIN@EXAMPLE.COM", "password": ADMIN_PASSWORD},
        follow_redirects=True,
    )
    assert b"Good to see you" in response.data


def test_wrong_password_is_rejected(app, client):
    create_admin(client)
    sign_out(client)

    response = client.post(
        "/login",
        data={"email": ADMIN_EMAIL, "password": "Wrong-Password-12345"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Invalid email address or password" in response.data
    assert b"Good to see you" not in response.data

    with app.app_context():
        user = db.session.scalar(select(User))
        assert user.failed_login_count == 1


def test_unknown_account_gets_generic_error(app, client):
    create_admin(client)
    sign_out(client)

    response = client.post(
        "/login",
        data={"email": "nobody@example.com", "password": "Wrong-Password-12345"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Invalid email address or password" in response.data


def test_account_locks_after_repeated_failures(app, client):
    create_admin(client)
    sign_out(client)

    for _ in range(3):
        client.post(
            "/login",
            data={"email": ADMIN_EMAIL, "password": "Wrong-Password-12345"},
        )

    with app.app_context():
        user = db.session.scalar(select(User))
        assert user.locked_until is not None

    response = client.post(
        "/login",
        data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 429
    assert b"temporarily locked" in response.data


def test_failed_and_successful_logins_are_audited(app, client):
    create_admin(client)
    sign_out(client)

    client.post(
        "/login",
        data={"email": ADMIN_EMAIL, "password": "Wrong-Password-12345"},
    )
    client.post(
        "/login",
        data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )

    with app.app_context():
        actions = set(db.session.scalars(select(AuditEvent.action)))
        assert "auth.logout" in actions
        assert "auth.login.failed" in actions
        assert "auth.login.succeeded" in actions


def test_open_redirect_is_ignored(client):
    create_admin(client)
    sign_out(client)

    response = client.post(
        "/login?next=https://evil.example.com",
        data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "evil.example.com" not in response.headers["Location"]
    assert response.headers["Location"].endswith("/dashboard")


def test_safe_relative_redirect_is_honored(client):
    create_admin(client)
    sign_out(client)

    response = client.post(
        "/login?next=/dashboard",
        data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")


def test_logout_requires_post(client):
    create_admin(client)
    response = client.get("/logout")
    assert response.status_code in (302, 405)


def test_health_check_reports_initialized(app, client):
    create_admin(client)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json()["initialized"] is True
