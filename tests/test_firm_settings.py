"""Firm settings, branding, and secure logo upload tests."""

from __future__ import annotations

import os
import stat
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from sqlalchemy import inspect, select

from openlawoffice.branding import STORED_NAME_RE
from openlawoffice.extensions import db
from openlawoffice.models import (
    ROLE_MEMBER,
    AuditEvent,
    Firm,
    User,
    utcnow,
)

from .conftest import (
    ADMIN_NAME,
    create_admin,
    make_app,
)


def make_image(
    fmt: str = "PNG",
    size: tuple[int, int] = (200, 100),
    color: tuple[int, int, int] = (19, 44, 63),
    comment: str | None = None,
) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = BytesIO()
    if comment and fmt == "PNG":
        metadata = PngInfo()
        metadata.add_text("Comment", comment)
        image.save(buffer, format="PNG", pnginfo=metadata)
    else:
        image.save(buffer, format=fmt)
    return buffer.getvalue()


def upload_logo(
    client,
    data: bytes,
    filename: str,
    *,
    name: str = "Ada Attorney",
    content_type: str = "image/png",
    **extra,
):
    return client.post(
        "/settings/firm",
        data={
            "name": name,
            "logo": (BytesIO(data), filename, content_type),
            **extra,
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def test_firm_table_is_created_at_startup(app):
    with app.app_context():
        assert inspect(db.engine).has_table("firms")


def test_setup_creates_firm_from_admin_name(app, client):
    create_admin(client)

    with app.app_context():
        firm = db.session.scalar(select(Firm))
        user = db.session.scalar(select(User))
        assert firm is not None
        assert firm.name == ADMIN_NAME
        assert firm.updated_by_id == user.id
        assert firm.logo_stored_name is None


def test_anonymous_user_is_redirected_to_login(client):
    create_admin(client)
    client.post("/logout")

    response = client.get("/settings/firm")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_non_admin_cannot_view_firm_settings(app, client):
    create_admin(client)
    with app.app_context():
        member = User(
            email="member@example.com",
            full_name="Mia Member",
            role=ROLE_MEMBER,
            active=True,
        )
        member.set_password("Member-Password-42")
        db.session.add(member)
        db.session.commit()

    client.post("/logout")
    client.post(
        "/login",
        data={"identifier": "member@example.com", "password": "Member-Password-42"},
    )

    response = client.get("/settings/firm")
    assert response.status_code == 403

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert b"/settings/firm" not in dashboard.data


def test_settings_page_prefills_admin_name(client):
    create_admin(client)

    response = client.get("/settings/firm")
    assert response.status_code == 200
    assert b"Firm settings" in response.data
    assert ADMIN_NAME.encode() in response.data
    assert b"Remove the current logo" not in response.data


def test_update_firm_settings_normalizes_fields(app, client):
    create_admin(client)

    response = client.post(
        "/settings/firm",
        data={
            "name": "  Attorney & Associates  ",
            "address_line_1": "123 Main Street",
            "address_line_2": "Suite 400",
            "city": "Springfield",
            "state": "IL",
            "postal_code": "627041234",
            "telephone": "1 (217) 555-0100",
            "email": "FIRM@EXAMPLE.COM",
            "website": "example.com",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Firm settings saved" in response.data

    with app.app_context():
        firm = db.session.scalar(select(Firm))
        assert firm.name == "Attorney & Associates"
        assert firm.address_line_1 == "123 Main Street"
        assert firm.address_line_2 == "Suite 400"
        assert firm.city == "Springfield"
        assert firm.state == "IL"
        assert firm.postal_code == "62704-1234"
        assert firm.telephone == "(217) 555-0100"
        assert firm.email == "firm@example.com"
        assert firm.website == "https://example.com"
        assert firm.address_lines == [
            "123 Main Street",
            "Suite 400",
            "Springfield, IL 62704-1234",
        ]

        event = db.session.scalar(
            select(AuditEvent).where(AuditEvent.action == "firm.updated")
        )
        assert event is not None
        assert "telephone" in event.detail["fields"]
        assert "logo" not in event.detail


def test_dashboard_firm_checklist_updates_after_change(client):
    create_admin(client)

    before = client.get("/dashboard")
    assert b'data-checklist-item="firm-settings"' in before.data
    assert b'data-complete="false"' in before.data

    response = client.post(
        "/settings/firm",
        data={
            "name": "Ada Attorney",
            "address_line_1": "123 Main Street",
        },
        follow_redirects=True,
    )
    assert b"Firm settings saved" in response.data

    after = client.get("/dashboard")
    assert b'data-checklist-item="firm-settings"' in after.data
    assert b'data-complete="true"' in after.data
    assert b"Firm details are saved and used across the app." in after.data


def test_unchanged_firm_settings_do_not_complete_checklist(client):
    create_admin(client)

    response = client.post(
        "/settings/firm",
        data={"name": ADMIN_NAME},
        follow_redirects=True,
    )
    assert b"No changes to save" in response.data

    dashboard = client.get("/dashboard")
    assert b'data-complete="false"' in dashboard.data


def test_only_firm_name_is_required(app, client):
    create_admin(client)

    response = client.post(
        "/settings/firm",
        data={"name": "Minimal Firm"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Firm settings saved" in response.data

    with app.app_context():
        firm = db.session.scalar(select(Firm))
        assert firm.name == "Minimal Firm"
        assert firm.address_line_1 is None
        assert firm.telephone is None
        assert firm.website is None


def test_missing_name_is_rejected(app, client):
    create_admin(client)
    response = client.post("/settings/firm", data={"name": "   "})
    assert response.status_code == 200
    assert b"This field is required" in response.data

    with app.app_context():
        firm = db.session.scalar(select(Firm))
        assert firm.name == ADMIN_NAME


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("postal_code", "1234", b"5-digit ZIP"),
        ("telephone", "555-1234", b"10-digit U.S. telephone"),
        ("website", "javascript:alert(1)", b"HTTP or HTTPS"),
        ("website", "ftp://example.com", b"HTTP or HTTPS"),
        ("state", "ZZ", b"Not a valid choice"),
    ],
)
def test_invalid_fields_are_rejected(client, field, value, message):
    create_admin(client)

    data = {"name": "Ada Attorney", field: value}
    response = client.post("/settings/firm", data=data)
    assert response.status_code == 200
    assert message in response.data


def test_member_cannot_post_firm_settings(app, client):
    create_admin(client)
    with app.app_context():
        member = User(
            email="member@example.com",
            full_name="Mia Member",
            role=ROLE_MEMBER,
            active=True,
        )
        member.set_password("Member-Password-42")
        db.session.add(member)
        db.session.commit()

    client.post("/logout")
    client.post(
        "/login",
        data={"identifier": "member@example.com", "password": "Member-Password-42"},
    )

    response = client.post(
        "/settings/firm",
        data={"name": "Member Takeover"},
    )
    assert response.status_code == 403

    with app.app_context():
        firm = db.session.scalar(select(Firm))
        assert firm.name == ADMIN_NAME


def test_existing_install_creates_firm_on_first_visit(app, client):
    with app.app_context():
        user = User(
            email="old@example.com",
            full_name="Existing Owner",
            role="admin",
            active=True,
            last_login_at=utcnow(),
        )
        user.set_password("Existing-Password-42")
        db.session.add(user)
        db.session.commit()

    client.post(
        "/login",
        data={"identifier": "old@example.com", "password": "Existing-Password-42"},
    )

    response = client.get("/settings/firm")
    assert response.status_code == 200
    assert b"Existing Owner" in response.data

    with app.app_context():
        firm = db.session.scalar(select(Firm))
        assert firm is not None
        assert firm.name == "Existing Owner"


def test_logo_upload_is_sanitized_and_stored_securely(app, client):
    create_admin(client)

    source = make_image(
        "PNG",
        size=(2000, 1000),
        comment="secret-marker-do-not-keep",
    )
    response = upload_logo(client, source, "original-name.png")
    assert response.status_code == 200
    assert b"Firm settings saved" in response.data

    with app.app_context():
        firm = db.session.scalar(select(Firm))
        assert firm.has_logo
        assert STORED_NAME_RE.fullmatch(firm.logo_stored_name)
        assert "original-name" not in firm.logo_stored_name
        assert firm.logo_content_type == "image/png"
        assert (firm.logo_width, firm.logo_height) == (1600, 800)
        assert firm.logo_size_bytes <= app.config["FIRM_LOGO_MAX_BYTES"]
        assert firm.logo_sha256

        stored_path = Path(app.config["FIRM_LOGO_UPLOAD_DIR"]) / firm.logo_stored_name
        assert stored_path.is_file()
        assert stored_path.stat().st_size == firm.logo_size_bytes
        assert b"secret-marker-do-not-keep" not in stored_path.read_bytes()

        if os.name == "posix":
            assert stat.S_IMODE(stored_path.stat().st_mode) == 0o600
            assert (
                stat.S_IMODE(Path(app.config["FIRM_LOGO_UPLOAD_DIR"]).stat().st_mode)
                == 0o700
            )

        with Image.open(stored_path) as stored_image:
            assert stored_image.size == (1600, 800)
            assert "Comment" not in stored_image.info


def test_logo_is_publicly_served(app, client):
    create_admin(client)
    source = make_image("PNG")
    upload_logo(client, source, "logo.png")

    with app.app_context():
        firm = db.session.scalar(select(Firm))
        expected_hash = firm.logo_sha256

    client.post("/logout")
    response = client.get("/branding/logo")
    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"].startswith("public")
    assert expected_hash in response.headers["ETag"]

    cached = client.get(
        "/branding/logo",
        headers={"If-None-Match": response.headers["ETag"]},
    )
    assert cached.status_code == 304


def test_login_page_uses_firm_name_and_logo(app, client):
    create_admin(client)
    upload_logo(client, make_image("PNG"), "logo.png")
    client.post("/logout")

    response = client.get("/login")
    assert response.status_code == 200
    assert ADMIN_NAME.encode() in response.data
    assert b"/branding/logo" in response.data


def test_replacing_logo_removes_old_file(app, client):
    create_admin(client)
    upload_logo(client, make_image("PNG"), "first.png")

    with app.app_context():
        firm = db.session.scalar(select(Firm))
        first_name = firm.logo_stored_name
        first_path = Path(app.config["FIRM_LOGO_UPLOAD_DIR"]) / first_name
        assert first_path.is_file()

    response = upload_logo(
        client,
        make_image("JPEG", size=(300, 300)),
        "second.jpg",
        content_type="image/jpeg",
    )
    assert response.status_code == 200

    with app.app_context():
        firm = db.session.scalar(select(Firm))
        second_name = firm.logo_stored_name
        assert second_name != first_name
        assert firm.logo_content_type == "image/jpeg"
        assert not first_path.exists()
        assert (Path(app.config["FIRM_LOGO_UPLOAD_DIR"]) / second_name).is_file()


def test_removing_logo_deletes_file(app, client):
    create_admin(client)
    upload_logo(client, make_image("PNG"), "logo.png")

    with app.app_context():
        firm = db.session.scalar(select(Firm))
        logo_name = firm.logo_stored_name
        logo_path = Path(app.config["FIRM_LOGO_UPLOAD_DIR"]) / logo_name

    response = client.post(
        "/settings/firm",
        data={"name": "Ada Attorney", "remove_logo": "y"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Firm settings saved" in response.data

    with app.app_context():
        firm = db.session.scalar(select(Firm))
        assert not firm.has_logo
        assert firm.logo_stored_name is None
        assert not logo_path.exists()

        event = db.session.scalar(
            select(AuditEvent)
            .where(AuditEvent.action == "firm.updated")
            .order_by(AuditEvent.id.desc())
        )
        assert event.detail["logo"] == "removed"

    assert client.get("/branding/logo").status_code == 404


def test_logo_route_returns_404_without_logo(client):
    create_admin(client)
    assert client.get("/branding/logo").status_code == 404


def test_webp_logo_is_supported(app, client):
    create_admin(client)
    response = upload_logo(
        client,
        make_image("WEBP", size=(300, 150)),
        "logo.webp",
        content_type="image/webp",
    )
    assert response.status_code == 200
    assert b"Firm settings saved" in response.data

    with app.app_context():
        firm = db.session.scalar(select(Firm))
        assert firm.logo_content_type == "image/webp"
        assert (firm.logo_width, firm.logo_height) == (300, 150)


def test_invalid_logo_is_rejected(app, client):
    create_admin(client)
    response = upload_logo(
        client,
        b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
        "attack.png",
    )
    assert response.status_code == 200
    assert b"not a valid PNG, JPEG, or WebP image" in response.data

    with app.app_context():
        firm = db.session.scalar(select(Firm))
        assert not firm.has_logo


def test_oversized_logo_is_rejected(app, client):
    create_admin(client)
    oversized = b"0" * (app.config["FIRM_LOGO_MAX_BYTES"] + 1)
    response = upload_logo(client, oversized, "huge.png")
    assert response.status_code == 200
    assert b"2 MB or smaller" in response.data

    with app.app_context():
        firm = db.session.scalar(select(Firm))
        assert not firm.has_logo


def test_too_many_pixels_is_rejected(app, client):
    create_admin(client)
    app.config["FIRM_LOGO_MAX_PIXELS"] = 10_000
    response = upload_logo(client, make_image("PNG", size=(200, 100)), "large.png")
    assert response.status_code == 200
    assert b"dimensions are too large" in response.data

    with app.app_context():
        firm = db.session.scalar(select(Firm))
        assert not firm.has_logo


def test_cannot_upload_and_remove_logo_together(app, client):
    create_admin(client)
    upload_logo(client, make_image("PNG"), "logo.png")

    response = upload_logo(
        client,
        make_image("PNG"),
        "replacement.png",
        remove_logo="y",
    )
    assert response.status_code == 200
    assert b"either a new logo or removal" in response.data

    with app.app_context():
        firm = db.session.scalar(select(Firm))
        assert firm.has_logo


def test_settings_page_does_not_show_remove_option_without_logo(client):
    create_admin(client)
    response = client.get("/settings/firm")
    assert b"Remove the current logo" not in response.data


def test_firm_table_survives_existing_database_restart(tmp_path):
    first_app = make_app(tmp_path)
    with first_app.app_context():
        assert inspect(db.engine).has_table("firms")
        db.session.remove()
        db.drop_all()

    second_app = make_app(tmp_path)
    with second_app.app_context():
        assert inspect(db.engine).has_table("firms")
