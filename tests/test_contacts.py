"""Contact management and import tests."""

from __future__ import annotations

from io import BytesIO

from sqlalchemy import func, select

from openlawoffice.extensions import db
from openlawoffice.models import ROLE_MEMBER, AuditEvent, Contact, User

from .conftest import create_admin

MEMBER_PASSWORD = "Member-Password-42"


def contact_payload(
    *,
    first_name: str = "Jane",
    last_name: str = "Contact",
    organization: str = "Acme Law",
    **extra,
):
    return {
        "first_name": first_name,
        "last_name": last_name,
        "organization": organization,
        "email": "jane@example.com",
        **extra,
    }


def create_contact(client, **overrides):
    return client.post(
        "/contacts/new",
        data=contact_payload(**overrides),
        follow_redirects=True,
    )


def import_contacts(client, filename: str, content: str | bytes):
    if isinstance(content, str):
        content = content.encode("utf-8")
    return client.post(
        "/contacts/import",
        data={"file": (BytesIO(content), filename)},
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def add_member(app, *, email="member@example.com", username="member"):
    with app.app_context():
        member = User(
            username=username,
            full_name="Mia Member",
            email=email,
            professional_role="Associate",
            role=ROLE_MEMBER,
            active=True,
        )
        member.set_password(MEMBER_PASSWORD)
        db.session.add(member)
        db.session.commit()


VCF_SAMPLE = """BEGIN:VCARD
VERSION:3.0
FN:Jane Q. Contact
N:Contact;Jane;Q.;;
ORG:Acme Law;Litigation
TITLE:Partner
EMAIL;TYPE=WORK:Jane@Example.com
TEL;TYPE=WORK:+1 217 555 0100
TEL;TYPE=CELL:+1 217 555 0199
ADR;TYPE=WORK:;;123 Main St;Springfield;IL;62704;USA
NOTE:Met at conference.
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN:Bob Brown
N:Brown;Bob;;;
EMAIL:bob@example.com
END:VCARD
"""

GOOGLE_CSV = """Name,Given Name,Family Name,Organization Name,Organization Title,E-mail 1 - Value,Phone 1 - Value,Address 1 - Street,Address 1 - City,Address 1 - Region,Address 1 - Postal Code,Address 1 - Country,Notes
Jane Contact,Jane,Contact,Acme Law,Partner,jane@example.com,217-555-0100,123 Main St,Springfield,IL,62704,USA,Google contact
"""

OUTLOOK_CSV = """First Name,Last Name,Company,Job Title,E-mail Address,Business Phone,Mobile Phone,Business Street,Business City,Business State,Business Postal Code,Business Country/Region,Notes
John,Smith,Smith & Co,Attorney,john@example.com,217-555-0111,217-555-0122,456 Oak Ave,Chicago,IL,60601,USA,Outlook contact
"""

ICS_SAMPLE = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
SUMMARY:Case conference
ORGANIZER;CN=Jane Doe:mailto:jane@example.com
ATTENDEE;CN="Smith, John";EMAIL=john@example.com:mailto:john@example.com
ATTENDEE;CN="Smith, John";EMAIL=john@example.com:mailto:john@example.com
END:VEVENT
END:VCALENDAR
"""


def test_contact_list_requires_login(client):
    create_admin(client)
    client.post("/logout")
    response = client.get("/contacts", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_create_contact_and_view_detail(app, client):
    create_admin(client)

    response = create_contact(
        client,
        phone="217-555-0100",
        notes="Met at a conference.",
    )
    assert response.status_code == 200
    assert b"Jane Contact" in response.data
    assert b"Acme Law" in response.data
    assert b"jane@example.com" in response.data

    with app.app_context():
        contact = db.session.scalar(select(Contact))
        assert contact is not None
        assert contact.first_name == "Jane"
        assert contact.last_name == "Contact"
        assert contact.organization == "Acme Law"
        assert contact.email == "jane@example.com"
        assert contact.phone == "217-555-0100"
        assert contact.notes == "Met at a conference."
        assert contact.source == "manual"
        assert contact.created_by is not None

        event = db.session.scalar(
            select(AuditEvent).where(AuditEvent.action == "contact.created")
        )
        assert event is not None


def test_contact_requires_name_or_organization(app, client):
    create_admin(client)
    response = client.post(
        "/contacts/new",
        data={"first_name": "", "last_name": "", "organization": ""},
    )
    assert response.status_code == 200
    assert b"Enter a first name, last name, or organization" in response.data

    with app.app_context():
        assert db.session.scalar(select(Contact.id)) is None


def test_contact_optional_fields_and_normalization(app, client):
    create_admin(client)

    response = create_contact(
        client,
        email="JANE@EXAMPLE.COM",
        phone="+1 217 555 0100",
        mobile="217-555-0199",
        address_line_1="123 Main St",
        city="Springfield",
        state="IL",
        postal_code="62704",
        country="USA",
    )
    assert response.status_code == 200

    with app.app_context():
        contact = db.session.scalar(select(Contact))
        assert contact.email == "jane@example.com"
        assert contact.mobile == "217-555-0199"
        assert contact.address_lines == [
            "123 Main St",
            "Springfield, IL 62704",
            "USA",
        ]


def test_edit_contact(app, client):
    create_admin(client)
    create_contact(client)

    with app.app_context():
        contact_id = db.session.scalar(select(Contact.id))

    response = client.post(
        f"/contacts/{contact_id}/edit",
        data={
            "first_name": "Janet",
            "last_name": "Contact",
            "organization": "Acme Law",
            "job_title": "Managing Partner",
            "email": "janet@example.com",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Janet Contact" in response.data

    with app.app_context():
        contact = db.session.get(Contact, contact_id)
        assert contact.first_name == "Janet"
        assert contact.job_title == "Managing Partner"
        assert contact.email == "janet@example.com"
        event = db.session.scalar(
            select(AuditEvent).where(AuditEvent.action == "contact.updated")
        )
        assert event is not None


def test_contact_search_and_pagination(app, client):
    create_admin(client)

    with app.app_context():
        for index in range(45):
            db.session.add(
                Contact(
                    first_name=f"Person{index:02d}",
                    last_name="Searchable",
                    organization="Bulk Org",
                    email=f"person{index}@example.com",
                    source="manual",
                )
            )
        db.session.add(
            Contact(
                first_name="Unique",
                last_name="Findme",
                organization="Distinct Firm",
                email="unique@example.com",
                source="manual",
            )
        )
        db.session.commit()

    first_page = client.get("/contacts")
    assert first_page.status_code == 200
    assert b"Page 1 of 2" in first_page.data

    second_page = client.get("/contacts?page=2")
    assert second_page.status_code == 200
    assert b"Page 2 of 2" in second_page.data

    search = client.get("/contacts?q=Distinct")
    assert search.status_code == 200
    assert b"Unique Findme" in search.data
    assert b"Bulk Org" not in search.data


def test_delete_contact_requires_confirmation(app, client):
    create_admin(client)
    create_contact(client)

    with app.app_context():
        contact_id = db.session.scalar(select(Contact.id))

    warning = client.get(f"/contacts/{contact_id}/delete")
    assert warning.status_code == 200
    assert b"Delete Jane Contact?" in warning.data

    with app.app_context():
        assert db.session.get(Contact, contact_id) is not None

    response = client.post(
        f"/contacts/{contact_id}/delete",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"No contacts yet" in response.data

    with app.app_context():
        assert db.session.get(Contact, contact_id) is None
        event = db.session.scalar(
            select(AuditEvent).where(AuditEvent.action == "contact.deleted")
        )
        assert event is not None


def test_member_can_manage_contacts(app, client):
    create_admin(client)
    add_member(app)
    client.post("/logout")
    client.post(
        "/login",
        data={"identifier": "member", "password": MEMBER_PASSWORD},
        follow_redirects=True,
    )

    response = create_contact(client)
    assert response.status_code == 200
    assert b"Jane Contact" in response.data


def test_import_vcard_and_skip_duplicates(app, client):
    create_admin(client)

    response = import_contacts(client, "contacts.vcf", VCF_SAMPLE)
    assert response.status_code == 200
    assert b"Imported 2 contacts" in response.data

    with app.app_context():
        contacts = db.session.scalars(
            select(Contact).order_by(Contact.first_name)
        ).all()
        assert len(contacts) == 2
        jane = db.session.scalar(
            select(Contact).where(Contact.email == "jane@example.com")
        )
        assert jane is not None
        assert jane.first_name == "Jane"
        assert jane.last_name == "Contact"
        assert jane.organization == "Acme Law"
        assert jane.job_title == "Partner"
        assert jane.email == "jane@example.com"
        assert jane.phone == "+1 217 555 0100"
        assert jane.mobile == "+1 217 555 0199"
        assert jane.address_line_1 == "123 Main St"
        assert jane.city == "Springfield"
        assert jane.source == "vcard"
        assert jane.notes == "Met at conference."

        event = db.session.scalar(
            select(AuditEvent).where(AuditEvent.action == "contact.imported")
        )
        assert event is not None
        assert event.detail["created"] == 2
        assert event.detail["source"] == "vcard"

    second = import_contacts(client, "contacts.vcf", VCF_SAMPLE)
    assert second.status_code == 200
    assert b"No new contacts were imported" in second.data

    with app.app_context():
        assert db.session.scalar(select(func.count(Contact.id))) == 2


def test_import_google_csv(app, client):
    create_admin(client)

    response = import_contacts(client, "google.csv", GOOGLE_CSV)
    assert response.status_code == 200
    assert b"Imported 1 contact" in response.data

    with app.app_context():
        contact = db.session.scalar(select(Contact))
        assert contact.first_name == "Jane"
        assert contact.last_name == "Contact"
        assert contact.organization == "Acme Law"
        assert contact.job_title == "Partner"
        assert contact.email == "jane@example.com"
        assert contact.phone == "217-555-0100"
        assert contact.address_line_1 == "123 Main St"
        assert contact.city == "Springfield"
        assert contact.state == "IL"
        assert contact.postal_code == "62704"
        assert contact.country == "USA"
        assert contact.notes == "Google contact"
        assert contact.source == "csv"


def test_import_outlook_csv(app, client):
    create_admin(client)

    response = import_contacts(client, "outlook.csv", OUTLOOK_CSV)
    assert response.status_code == 200

    with app.app_context():
        contact = db.session.scalar(select(Contact))
        assert contact.first_name == "John"
        assert contact.last_name == "Smith"
        assert contact.organization == "Smith & Co"
        assert contact.email == "john@example.com"
        assert contact.phone == "217-555-0111"
        assert contact.mobile == "217-555-0122"
        assert contact.address_line_1 == "456 Oak Ave"
        assert contact.city == "Chicago"
        assert contact.source == "csv"


def test_import_calendar_attendees(app, client):
    create_admin(client)

    response = import_contacts(client, "calendar.ics", ICS_SAMPLE)
    assert response.status_code == 200
    assert b"Imported 2 contacts" in response.data

    with app.app_context():
        contacts = db.session.scalars(select(Contact).order_by(Contact.email)).all()
        assert [contact.email for contact in contacts] == [
            "jane@example.com",
            "john@example.com",
        ]
        assert contacts[0].first_name == "Jane"
        assert contacts[0].last_name == "Doe"
        assert contacts[1].first_name == "John"
        assert contacts[1].last_name == "Smith"
        assert all(contact.source == "ics" for contact in contacts)


def test_import_invalid_files(client):
    create_admin(client)

    bad_vcard = import_contacts(client, "bad.vcf", "not a vcard")
    assert bad_vcard.status_code == 200
    assert b"not a valid vCard" in bad_vcard.data

    bad_calendar = import_contacts(
        client, "bad.ics", "BEGIN:VCALENDAR\nEND:VCALENDAR\n"
    )
    assert bad_calendar.status_code == 200
    assert b"No attendee or organizer" in bad_calendar.data

    bad_csv = import_contacts(client, "bad.csv", "foo,bar\n1,2\n")
    assert bad_csv.status_code == 200
    assert b"Could not recognize contact columns" in bad_csv.data

    empty = import_contacts(client, "empty.csv", "")
    assert empty.status_code == 200
    assert b"uploaded file is empty" in empty.data


def test_import_skips_existing_contact_email(app, client):
    create_admin(client)
    create_contact(client)

    response = import_contacts(client, "google.csv", GOOGLE_CSV)
    assert response.status_code == 200
    assert b"No new contacts were imported" in response.data

    with app.app_context():
        assert db.session.scalar(select(func.count(Contact.id))) == 1
