"""User management and legacy schema upgrade tests."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from sqlalchemy import inspect, select
from werkzeug.security import generate_password_hash

from openlawoffice.extensions import db
from openlawoffice.matter_seed import normalize_matter_type_name
from openlawoffice.models import (
    ROLE_MEMBER,
    AuditEvent,
    Matter,
    MatterType,
    User,
)

from .conftest import ADMIN_NAME, ADMIN_USERNAME, create_admin, make_app

USER_PASSWORD = "User-Password-42"


def add_member(
    app,
    *,
    username: str = "member",
    full_name: str = "Mia Member",
    email: str = "member@example.com",
    professional_role: str = "Associate",
    password: str = USER_PASSWORD,
) -> int:
    with app.app_context():
        user = User(
            username=username,
            full_name=full_name,
            email=email,
            professional_role=professional_role,
            role=ROLE_MEMBER,
            active=True,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user.id


def create_user_through_form(
    client,
    *,
    username: str = "jdoe",
    full_name: str = "Jordan Doe",
    email: str = "jdoe@example.com",
    password: str = USER_PASSWORD,
    follow_redirects: bool = True,
    **extra,
):
    return client.post(
        "/settings/users/new",
        data={
            "username": username,
            "full_name": full_name,
            "email": email,
            "password": password,
            "confirm_password": password,
            **extra,
        },
        follow_redirects=follow_redirects,
    )


def test_admin_can_view_user_list(client):
    create_admin(client)
    response = client.get("/settings/users")
    assert response.status_code == 200
    assert ADMIN_USERNAME.encode() in response.data
    assert ADMIN_NAME.encode() in response.data
    assert b"Administrator" in response.data
    assert b"New user" in response.data


def test_member_cannot_access_user_management(app, client):
    create_admin(client)
    add_member(app)
    client.post("/logout")
    client.post(
        "/login",
        data={"identifier": "member", "password": USER_PASSWORD},
        follow_redirects=True,
    )

    assert client.get("/settings/users").status_code == 403
    assert client.get("/settings/users/new").status_code == 403
    assert client.post("/settings/users/new", data={}).status_code == 403


def test_create_user_with_required_fields_only(app, client):
    create_admin(client)

    response = create_user_through_form(client)
    assert response.status_code == 200
    assert b"jdoe" in response.data
    assert b"created." in response.data

    with app.app_context():
        user = db.session.scalar(select(User).where(User.username == "jdoe"))
        assert user is not None
        assert user.full_name == "Jordan Doe"
        assert user.email == "jdoe@example.com"
        assert user.telephone is None
        assert user.office is None
        assert user.department is None
        assert user.professional_role == "Associate"
        assert user.role == ROLE_MEMBER
        assert user.active is True
        assert user.check_password(USER_PASSWORD)

        event = db.session.scalar(
            select(AuditEvent).where(AuditEvent.action == "user.created")
        )
        assert event is not None
        assert event.detail["username"] == "jdoe"


def test_create_user_normalizes_fields(app, client):
    create_admin(client)

    response = create_user_through_form(
        client,
        username="  JDOE  ",
        email="JDOE@EXAMPLE.COM",
        telephone="1 (217) 555-0100",
        office=" Springfield ",
        professional_role="Partner",
        department=" Litigation ",
    )
    assert response.status_code == 200

    with app.app_context():
        user = db.session.scalar(select(User).where(User.username == "jdoe"))
        assert user is not None
        assert user.email == "jdoe@example.com"
        assert user.telephone == "(217) 555-0100"
        assert user.office == "Springfield"
        assert user.professional_role == "Partner"
        assert user.department == "Litigation"


def test_create_user_validation(app, client):
    create_admin(client)
    create_user_through_form(client)

    duplicate_username = create_user_through_form(
        client,
        username="JDOE",
        email="other@example.com",
        follow_redirects=False,
    )
    assert duplicate_username.status_code == 200
    assert b"That username is already in use" in duplicate_username.data

    duplicate_email = create_user_through_form(
        client,
        username="other",
        email="JDOE@EXAMPLE.COM",
        follow_redirects=False,
    )
    assert duplicate_email.status_code == 200
    assert b"That email address is already in use" in duplicate_email.data

    invalid_username = create_user_through_form(
        client,
        username="bad name",
        email="bad@example.com",
        follow_redirects=False,
    )
    assert invalid_username.status_code == 200
    assert b"lowercase letters" in invalid_username.data

    invalid_phone = create_user_through_form(
        client,
        username="badphone",
        email="badphone@example.com",
        telephone="555-1234",
        follow_redirects=False,
    )
    assert invalid_phone.status_code == 200
    assert b"10-digit U.S. telephone" in invalid_phone.data

    weak_password = create_user_through_form(
        client,
        username="weakpass",
        email="weakpass@example.com",
        password="short",
        follow_redirects=False,
    )
    assert weak_password.status_code == 200
    assert b"at least 12 characters" in weak_password.data

    with app.app_context():
        assert db.session.scalar(select(User).where(User.username == "other")) is None


def test_admin_can_edit_user(app, client):
    create_admin(client)
    user_id = add_member(app, username="jdoe", email="jdoe@example.com")

    response = client.get(f"/settings/users/{user_id}/edit")
    assert response.status_code == 200
    assert b"Mia Member" in response.data

    response = client.post(
        f"/settings/users/{user_id}/edit",
        data={
            "username": "jordan",
            "full_name": "Jordan Doe",
            "email": "jordan@example.com",
            "telephone": "217-555-0199",
            "office": "Chicago",
            "professional_role": "Of Counsel",
            "department": "Appeals",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"jordan" in response.data
    assert b"updated." in response.data

    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.username == "jordan"
        assert user.full_name == "Jordan Doe"
        assert user.email == "jordan@example.com"
        assert user.telephone == "(217) 555-0199"
        assert user.office == "Chicago"
        assert user.professional_role == "Of Counsel"
        assert user.department == "Appeals"

        event = db.session.scalar(
            select(AuditEvent).where(AuditEvent.action == "user.updated")
        )
        assert event is not None
        assert "professional_role" in event.detail["fields"]


def test_reset_password_clears_lockout_and_allows_login(app, client):
    create_admin(client)
    user_id = add_member(app, username="member", email="member@example.com")

    with app.app_context():
        user = db.session.get(User, user_id)
        user.failed_login_count = 2
        user.locked_until = datetime.now(UTC) + timedelta(minutes=15)
        db.session.commit()

    response = client.post(
        f"/settings/users/{user_id}/reset-password",
        data={
            "password": "New-Orchard-Signal-73",
            "confirm_password": "New-Orchard-Signal-73",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Password reset" in response.data

    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.check_password("New-Orchard-Signal-73")
        assert user.failed_login_count == 0
        assert user.locked_until is None
        event = db.session.scalar(
            select(AuditEvent).where(AuditEvent.action == "user.password_reset")
        )
        assert event is not None

    client.post("/logout")
    login = client.post(
        "/login",
        data={"identifier": "member", "password": "New-Orchard-Signal-73"},
        follow_redirects=True,
    )
    assert b"Good to see you" in login.data


def test_delete_warning_and_delete_user(app, client):
    create_admin(client)
    user_id = add_member(app, username="deleteme", email="deleteme@example.com")

    with app.app_context():
        matter_type = db.session.scalar(
            select(MatterType).where(
                MatterType.normalized_name == normalize_matter_type_name("Family Law")
            )
        )
        matter = Matter(
            title="Attributed Matter",
            matter_type_id=matter_type.id,
            jurisdiction="IL",
            created_by_id=user_id,
        )
        db.session.add(matter)
        db.session.commit()
        matter_id = matter.id

    warning = client.get(f"/settings/users/{user_id}/delete")
    assert warning.status_code == 200
    assert b"Delete Mia Member?" in warning.data
    assert b"deleteme" in warning.data
    assert b"permanently" in warning.data

    with app.app_context():
        assert db.session.get(User, user_id) is not None

    response = client.post(
        f"/settings/users/{user_id}/delete",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"deleted" in response.data

    with app.app_context():
        assert db.session.get(User, user_id) is None
        db.session.expire_all()
        matter = db.session.get(Matter, matter_id)
        assert matter.created_by_id is None

        event = db.session.scalar(
            select(AuditEvent).where(AuditEvent.action == "user.deleted")
        )
        assert event is not None
        assert event.detail["username"] == "deleteme"


def test_admin_cannot_delete_own_account(app, client):
    create_admin(client)
    with app.app_context():
        admin = db.session.scalar(select(User))
        admin_id = admin.id

    warning = client.get(f"/settings/users/{admin_id}/delete", follow_redirects=True)
    assert warning.status_code == 200
    assert b"You cannot delete your own account" in warning.data

    response = client.post(
        f"/settings/users/{admin_id}/delete",
        follow_redirects=True,
    )
    assert b"You cannot delete your own account" in response.data

    with app.app_context():
        assert db.session.get(User, admin_id) is not None


def test_legacy_database_gets_profile_columns_and_usernames(tmp_path):
    database_path = tmp_path / "test.db"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE users (
            id INTEGER NOT NULL PRIMARY KEY,
            email VARCHAR(255) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            full_name VARCHAR(120) NOT NULL,
            role VARCHAR(20) NOT NULL,
            active BOOLEAN NOT NULL,
            failed_login_count INTEGER NOT NULL,
            locked_until DATETIME,
            last_login_at DATETIME,
            password_changed_at DATETIME,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        );
        CREATE UNIQUE INDEX ix_users_email ON users (email);
        """
    )
    password_hash = generate_password_hash(USER_PASSWORD)
    for user_id, email, full_name, role in (
        (1, "legacy@example.com", "Legacy Admin", "admin"),
        (2, "legacy@other.com", "Legacy User", "member"),
    ):
        connection.execute(
            """
            INSERT INTO users (
                id, email, password_hash, full_name, role, active,
                failed_login_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 1, 0, ?, ?)
            """,
            (
                user_id,
                email,
                password_hash,
                full_name,
                role,
                "2026-01-01 00:00:00.000000",
                "2026-01-01 00:00:00.000000",
            ),
        )
    connection.commit()
    connection.close()

    app = make_app(tmp_path)
    with app.app_context():
        columns = {column["name"] for column in inspect(db.engine).get_columns("users")}
        assert {
            "username",
            "telephone",
            "office",
            "professional_role",
            "department",
        }.issubset(columns)

        users = db.session.scalars(select(User)).all()
        assert {user.username for user in users} == {"legacy", "legacy-2"}
        assert all(user.professional_role == "Associate" for user in users)

        indexes = inspect(db.engine).get_indexes("users")
        assert any(
            index.get("unique") and index.get("column_names") == ["username"]
            for index in indexes
        )

    client = app.test_client()
    response = client.post(
        "/login",
        data={"identifier": "legacy", "password": USER_PASSWORD},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Good to see you" in response.data
