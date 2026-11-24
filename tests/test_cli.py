"""CLI command behavior."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from openlawoffice.extensions import db
from openlawoffice.models import User

from .conftest import ADMIN_PASSWORD, make_app


def test_create_admin_prompts_in_logical_order(app):
    runner = app.test_cli_runner()
    result = runner.invoke(
        args=["create-admin"],
        input=(
            "Grace Partner\n"
            "grace@example.com\n"
            "Quiet-Harbor-Lantern-84\n"
            "Quiet-Harbor-Lantern-84\n"
        ),
    )
    assert result.exit_code == 0, result.output
    assert "grace@example.com" in result.output

    with app.app_context():
        user = db.session.scalar(select(User))
        assert user is not None
        assert user.email == "grace@example.com"
        assert user.full_name == "Grace Partner"
        assert user.role == "admin"
        assert user.check_password("Quiet-Harbor-Lantern-84")


def test_create_admin_rejects_duplicate_email(app):
    runner = app.test_cli_runner()
    first = runner.invoke(
        args=["create-admin"],
        input=(
            "Grace Partner\n"
            "grace@example.com\n"
            "Quiet-Harbor-Lantern-84\n"
            "Quiet-Harbor-Lantern-84\n"
        ),
    )
    assert first.exit_code == 0

    second = runner.invoke(
        args=["create-admin"],
        input=(
            "Another Person\n"
            "grace@example.com\n"
            "Harbor-Quiet-Lantern-84\n"
            "Harbor-Quiet-Lantern-84\n"
        ),
    )
    assert second.exit_code != 0
    assert "already exists" in second.output


def test_reset_password_clears_lockout(app):
    runner = app.test_cli_runner()
    runner.invoke(
        args=["create-admin"],
        input=(
            "Grace Partner\n"
            "grace@example.com\n"
            "Quiet-Harbor-Lantern-84\n"
            "Quiet-Harbor-Lantern-84\n"
        ),
    )
    with app.app_context():
        user = db.session.scalar(select(User))
        user.failed_login_count = 5
        user.locked_until = datetime.now(UTC) + timedelta(minutes=15)
        db.session.commit()

    result = runner.invoke(
        args=[
            "reset-password",
            "--email",
            "grace@example.com",
            "--password",
            "New-Orchard-Signal-73",
        ]
    )
    assert result.exit_code == 0, result.output

    with app.app_context():
        user = db.session.scalar(select(User))
        assert user.failed_login_count == 0
        assert user.locked_until is None
        assert user.check_password("New-Orchard-Signal-73")


def test_setup_reports_unreachable_database(tmp_path):
    missing = tmp_path / "missing-directory" / "olo.db"
    app = make_app(tmp_path, SQLALCHEMY_DATABASE_URI=f"sqlite:///{missing}")
    client = app.test_client()

    response = client.get("/setup")
    assert response.status_code == 503
    assert b"could not reach" in response.data
    assert ADMIN_PASSWORD.encode() not in response.data
