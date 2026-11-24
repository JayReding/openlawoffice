"""Matter list, creation, and matter type tests."""

from __future__ import annotations

from sqlalchemy import func, select

from openlawoffice.extensions import db
from openlawoffice.matter_seed import (
    DEFAULT_MATTER_TYPES,
    normalize_matter_type_name,
    seed_default_matter_types,
)
from openlawoffice.models import (
    ROLE_ADMIN,
    ROLE_MEMBER,
    AuditEvent,
    Matter,
    MatterType,
    User,
)

from .conftest import ADMIN_NAME, create_admin


def matter_type_id(app, name: str) -> int:
    with app.app_context():
        matter_type = db.session.scalar(
            select(MatterType).where(
                MatterType.normalized_name == normalize_matter_type_name(name)
            )
        )
        assert matter_type is not None
        return matter_type.id


def create_member(
    app, client, *, email="member@example.com", password="Member-Password-42"
):
    with app.app_context():
        member = User(
            email=email,
            full_name="Mia Member",
            role=ROLE_MEMBER,
            active=True,
        )
        member.set_password(password)
        db.session.add(member)
        db.session.commit()

    client.post("/logout")
    return client.post(
        "/login",
        data={"identifier": email, "password": password},
        follow_redirects=True,
    )


def submit_matter(
    client,
    type_id: int,
    *,
    title: str = "Smith v. Jones",
    jurisdiction: str = "IL",
    description: str | None = "Representation in a contract dispute.",
    follow_redirects: bool = True,
):
    data = {
        "title": title,
        "matter_type_id": str(type_id),
        "jurisdiction": jurisdiction,
    }
    if description is not None:
        data["description"] = description
    return client.post(
        "/matters/new",
        data=data,
        follow_redirects=follow_redirects,
    )


def test_default_matter_types_are_seeded_idempotently(app):
    with app.app_context():
        types = db.session.scalars(select(MatterType)).all()
        assert len(types) == len(DEFAULT_MATTER_TYPES) == 33
        assert {matter_type.name for matter_type in types} == set(DEFAULT_MATTER_TYPES)
        assert all(matter_type.is_default for matter_type in types)
        assert all(matter_type.active for matter_type in types)

        assert seed_default_matter_types() == 0
        count = db.session.scalar(select(func.count(MatterType.id)))
        assert count == 33


def test_anonymous_user_is_redirected_from_matters(client):
    create_admin(client)
    client.post("/logout")

    for path in ("/matters", "/matters/new"):
        response = client.get(path)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


def test_admin_can_view_matter_type_settings(client):
    create_admin(client)
    response = client.get("/settings/matter-types")
    assert response.status_code == 200
    assert b"Add a custom type" in response.data
    assert b"Family Law" in response.data
    assert b"Built-in" in response.data


def test_member_cannot_view_matter_type_settings(app, client):
    create_admin(client)
    create_member(app, client)

    response = client.get("/settings/matter-types")
    assert response.status_code == 403

    response = client.post(
        "/settings/matter-types",
        data={"name": "Member Custom Type"},
    )
    assert response.status_code == 403

    with app.app_context():
        assert (
            db.session.scalar(
                select(MatterType).where(
                    MatterType.normalized_name == "member custom type"
                )
            )
            is None
        )


def test_admin_can_add_custom_matter_type(app, client):
    create_admin(client)

    response = client.post(
        "/settings/matter-types",
        data={"name": "  Aviation   Law  "},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Aviation Law" in response.data
    assert b"added." in response.data

    with app.app_context():
        matter_type = db.session.scalar(
            select(MatterType).where(MatterType.normalized_name == "aviation law")
        )
        assert matter_type is not None
        assert matter_type.name == "Aviation Law"
        assert matter_type.normalized_name == "aviation law"
        assert matter_type.is_default is False
        assert matter_type.active is True
        assert matter_type.created_by is not None
        assert matter_type.created_by.role == ROLE_ADMIN

        event = db.session.scalar(
            select(AuditEvent).where(AuditEvent.action == "matter_type.created")
        )
        assert event is not None
        assert event.detail["name"] == "Aviation Law"


def test_duplicate_custom_matter_type_is_rejected(app, client):
    create_admin(client)

    client.post("/settings/matter-types", data={"name": "Aviation Law"})
    response = client.post(
        "/settings/matter-types",
        data={"name": "aviation   law"},
    )
    assert response.status_code == 200
    assert b"already exists" in response.data

    with app.app_context():
        count = db.session.scalar(
            select(func.count(MatterType.id)).where(
                MatterType.normalized_name == "aviation law"
            )
        )
        assert count == 1


def test_custom_type_duplicate_of_inactive_type_is_rejected(app, client):
    create_admin(client)
    client.post("/settings/matter-types", data={"name": "Aviation Law"})

    with app.app_context():
        matter_type = db.session.scalar(
            select(MatterType).where(MatterType.normalized_name == "aviation law")
        )
        matter_type.active = False
        db.session.commit()

    response = client.post(
        "/settings/matter-types",
        data={"name": "Aviation Law"},
    )
    assert response.status_code == 200
    assert b"inactive" in response.data


def test_admin_can_deactivate_and_reactivate_matter_type(app, client):
    create_admin(client)
    type_id = matter_type_id(app, "Tax")

    response = client.post(
        f"/settings/matter-types/{type_id}/toggle",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"deactivated" in response.data

    with app.app_context():
        matter_type = db.session.get(MatterType, type_id)
        assert matter_type.active is False
        event = db.session.scalar(
            select(AuditEvent).where(AuditEvent.action == "matter_type.deactivated")
        )
        assert event is not None
        assert event.detail["matter_type_id"] == type_id

    response = client.post(
        f"/settings/matter-types/{type_id}/toggle",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"reactivated" in response.data

    with app.app_context():
        assert db.session.get(MatterType, type_id).active is True


def test_last_active_matter_type_cannot_be_deactivated(app, client):
    create_admin(client)

    with app.app_context():
        types = db.session.scalars(select(MatterType)).all()
        for matter_type in types[1:]:
            matter_type.active = False
        db.session.commit()
        last_type_id = types[0].id

    response = client.post(
        f"/settings/matter-types/{last_type_id}/toggle",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"At least one matter type must remain active" in response.data

    with app.app_context():
        assert db.session.get(MatterType, last_type_id).active is True


def test_inactive_types_are_hidden_from_matter_form(app, client):
    create_admin(client)
    client.post(
        "/settings/matter-types",
        data={"name": "Admiralty"},
        follow_redirects=True,
    )

    with app.app_context():
        matter_type = db.session.scalar(
            select(MatterType).where(MatterType.normalized_name == "admiralty")
        )
        matter_type.active = False
        db.session.commit()

    response = client.get("/matters/new")
    assert response.status_code == 200
    assert b"Family Law" in response.data
    assert b"Admiralty" not in response.data


def test_create_matter_with_default_type_and_dashboard_update(app, client):
    create_admin(client)
    type_id = matter_type_id(app, "Family Law")

    response = submit_matter(client, type_id)
    assert response.status_code == 200
    assert b"Smith v. Jones" in response.data
    assert b"Family Law" in response.data
    assert b"Illinois" in response.data
    assert b"Representation in a contract dispute." in response.data

    with app.app_context():
        matter = db.session.scalar(select(Matter))
        assert matter is not None
        assert matter.title == "Smith v. Jones"
        assert matter.matter_type_id == type_id
        assert matter.jurisdiction == "IL"
        assert matter.description == "Representation in a contract dispute."
        assert matter.created_by is not None
        assert matter.created_by.full_name == ADMIN_NAME

        event = db.session.scalar(
            select(AuditEvent).where(AuditEvent.action == "matter.created")
        )
        assert event is not None
        assert event.detail["matter_id"] == matter.id
        assert event.detail["matter_type"] == "Family Law"

    listing = client.get("/matters")
    assert listing.status_code == 200
    assert b"Smith v. Jones" in listing.data
    assert b"Family Law" in listing.data

    dashboard = client.get("/dashboard")
    assert b'data-checklist-item="first-matter"' in dashboard.data
    assert b'data-complete="true"' in dashboard.data
    assert b"View matters" in dashboard.data


def test_matter_description_is_optional(app, client):
    create_admin(client)
    type_id = matter_type_id(app, "Probate")

    response = submit_matter(
        client,
        type_id,
        title="Estate of Rivera",
        description=None,
    )
    assert response.status_code == 200
    assert b"Estate of Rivera" in response.data
    assert b"No description has been added" in response.data

    with app.app_context():
        matter = db.session.scalar(select(Matter))
        assert matter.description is None


def test_matter_title_is_required(app, client):
    create_admin(client)
    type_id = matter_type_id(app, "Civil")

    response = submit_matter(client, type_id, title="   ")
    assert response.status_code == 200
    assert b"This field is required" in response.data

    with app.app_context():
        assert db.session.scalar(select(Matter.id)) is None


def test_invalid_jurisdiction_is_rejected(app, client):
    create_admin(client)
    type_id = matter_type_id(app, "Civil")

    response = submit_matter(client, type_id, jurisdiction="ZZ")
    assert response.status_code == 200
    assert b"Not a valid choice" in response.data

    with app.app_context():
        assert db.session.scalar(select(Matter.id)) is None


def test_inactive_matter_type_cannot_be_used(app, client):
    create_admin(client)
    type_id = matter_type_id(app, "Criminal")

    with app.app_context():
        matter_type = db.session.get(MatterType, type_id)
        matter_type.active = False
        db.session.commit()

    response = submit_matter(client, type_id)
    assert response.status_code == 200
    assert b"Not a valid choice" in response.data

    with app.app_context():
        assert db.session.scalar(select(Matter.id)) is None


def test_description_length_is_limited(app, client):
    create_admin(client)
    type_id = matter_type_id(app, "Civil")

    response = submit_matter(client, type_id, description="x" * 10_001)
    assert response.status_code == 200
    assert b"Field cannot be longer than 10000 characters" in response.data

    with app.app_context():
        assert db.session.scalar(select(Matter.id)) is None


def test_member_can_view_matters_but_cannot_create_them(app, client):
    create_admin(client)
    type_id = matter_type_id(app, "Immigration")
    submit_matter(
        client,
        type_id,
        title="Visa Petition",
        description="Prepare and file a family-based petition.",
    )

    with app.app_context():
        matter = db.session.scalar(select(Matter))
        matter_id = matter.id

    create_member(app, client)

    listing = client.get("/matters")
    assert listing.status_code == 200
    assert b"Visa Petition" in listing.data
    assert b"New matter" not in listing.data

    detail = client.get(f"/matters/{matter_id}")
    assert detail.status_code == 200
    assert b"Visa Petition" in detail.data

    response = client.get("/matters/new")
    assert response.status_code == 403

    response = submit_matter(
        client,
        type_id,
        title="Member Created Matter",
        description="This must not be created.",
    )
    assert response.status_code == 403

    with app.app_context():
        assert db.session.scalar(select(func.count(Matter.id))) == 1


def test_member_empty_matter_list_has_no_create_action(app, client):
    create_admin(client)
    create_member(app, client)

    response = client.get("/matters")
    assert response.status_code == 200
    assert b"No matters yet" in response.data
    assert b"An administrator can create the first matter" in response.data
    assert b"New matter" not in response.data
    assert b"Create your first matter" not in response.data

    dashboard = client.get("/dashboard")
    assert b"Create your first matter" not in dashboard.data
    assert b"Add your first matter" not in dashboard.data


def test_matter_detail_returns_404_for_unknown_matter(client):
    create_admin(client)
    response = client.get("/matters/99999")
    assert response.status_code == 404


def test_custom_type_appears_in_matter_form(app, client):
    create_admin(client)
    client.post(
        "/settings/matter-types",
        data={"name": "Aviation Law"},
        follow_redirects=True,
    )

    response = client.get("/matters/new")
    assert response.status_code == 200
    assert b"Aviation Law" in response.data
