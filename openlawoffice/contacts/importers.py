"""Parsers for contact and calendar export files.

Supported inputs:

- vCard (``.vcf``) exports from Apple Contacts, Google Contacts, Outlook, and
  other standard sources.
- CSV exports from Google Contacts and Outlook.
- iCalendar (``.ics``) exports, where attendee and organizer email addresses are
  imported as contacts.

Uploaded files are parsed in memory. Nothing is written to disk.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path

import vobject
from email_validator import EmailNotValidError, validate_email

from ..security import normalize_email

MAX_CONTACTS_PER_IMPORT = 5_000
MAX_IMPORT_BYTES = 4 * 1024 * 1024


class ContactImportError(ValueError):
    """A user-facing import problem."""


@dataclass
class ImportedContact:
    first_name: str | None = None
    last_name: str | None = None
    organization: str | None = None
    job_title: str | None = None
    email: str | None = None
    phone: str | None = None
    mobile: str | None = None
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    notes: str | None = None

    @property
    def full_name(self) -> str:
        return " ".join(
            part for part in (self.first_name, self.last_name) if part
        ).strip()

    @property
    def display_name(self) -> str:
        return self.full_name or self.organization or self.email or ""


@dataclass
class ImportResult:
    source: str
    contacts: list[ImportedContact]
    invalid: int = 0
    skipped_in_file: int = 0


def _text(
    value, max_length: int | None = None, *, multiline: bool = False
) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    value = str(value).replace("\r\n", "\n").replace("\r", "\n")
    value = "".join(
        character for character in value if character in "\n\t" or ord(character) >= 32
    )
    if multiline:
        value = "\n".join(line.strip() for line in value.splitlines()).strip()
    else:
        value = " ".join(value.split())
    if not value:
        return None
    return value[:max_length] if max_length else value


def _email(value) -> str | None:
    value = _text(value)
    if not value:
        return None
    if value.lower().startswith("mailto:"):
        value = value[7:]
    try:
        result = validate_email(value, check_deliverability=False)
    except EmailNotValidError:
        return None
    return normalize_email(result.normalized)


def _split_full_name(value: str | None) -> tuple[str | None, str | None]:
    value = _text(value, 200)
    if not value:
        return None, None
    parts = value.split()
    if len(parts) == 1:
        return parts[0][:100], None
    return parts[0][:100], " ".join(parts[1:])[:100]


def _name_from_cn(value: str | None) -> tuple[str | None, str | None]:
    value = _text(value, 200)
    if not value:
        return None, None
    if "," in value:
        last, first = value.split(",", 1)
        return _text(first, 100), _text(last, 100)
    return _split_full_name(value)


def _decode(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            pass
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _has_identity(contact: ImportedContact) -> bool:
    return bool(contact.full_name or contact.organization or contact.email)


def _deduplicate(
    contacts: list[ImportedContact],
) -> tuple[list[ImportedContact], int]:
    deduplicated: list[ImportedContact] = []
    seen_emails: set[str] = set()
    seen_names: set[tuple[str, str]] = set()
    skipped = 0

    for contact in contacts:
        if contact.email:
            key = contact.email
            if key in seen_emails:
                skipped += 1
                continue
            seen_emails.add(key)
        else:
            name_key = (
                contact.full_name.casefold(),
                (contact.organization or "").casefold(),
            )
            if name_key != ("", "") and name_key in seen_names:
                skipped += 1
                continue
            seen_names.add(name_key)
        deduplicated.append(contact)

    return deduplicated, skipped


def _parse_vcard(text: str) -> tuple[list[ImportedContact], int]:
    try:
        cards = list(vobject.readComponents(text))
    except Exception as exc:
        raise ContactImportError(
            "The vCard file could not be read. Confirm it is a valid .vcf export."
        ) from exc

    if len(cards) > MAX_CONTACTS_PER_IMPORT:
        raise ContactImportError(
            f"Import at most {MAX_CONTACTS_PER_IMPORT:,} contacts at a time."
        )

    contacts: list[ImportedContact] = []
    invalid = 0
    for card in cards:
        try:
            first_name = None
            last_name = None
            name = getattr(card, "n", None)
            if name is not None and name.value is not None:
                first_name = _text(name.value.given, 100)
                last_name = _text(name.value.family, 100)
            full_name = _text(getattr(getattr(card, "fn", None), "value", None), 200)
            if not first_name and not last_name:
                first_name, last_name = _split_full_name(full_name)

            organization = None
            org = getattr(card, "org", None)
            if org is not None and org.value:
                organization = _text(org.value[0], 200)

            job_title = _text(getattr(getattr(card, "title", None), "value", None), 150)

            email = None
            for component in card.contents.get("email", []):
                email = _email(component.value)
                if email:
                    break

            phone = None
            mobile = None
            for component in card.contents.get("tel", []):
                number = _text(component.value, 50)
                if not number:
                    continue
                types = component.params.get("TYPE", [])
                if isinstance(types, str):
                    types = [types]
                type_text = " ".join(str(item) for item in types).upper()
                if "CELL" in type_text or "MOBILE" in type_text:
                    mobile = mobile or number
                else:
                    phone = phone or number

            address_line_1 = None
            address_line_2 = None
            city = None
            state = None
            postal_code = None
            country = None
            address = getattr(card, "adr", None)
            if address is not None and address.value is not None:
                value = address.value
                address_line_1 = _text(value.street, 150)
                address_line_2 = _text(value.extended or value.box, 150)
                city = _text(value.city, 100)
                state = _text(value.region, 100)
                postal_code = _text(value.code, 20)
                country = _text(value.country, 100)

            imported = ImportedContact(
                first_name=first_name,
                last_name=last_name,
                organization=organization,
                job_title=job_title,
                email=email,
                phone=phone,
                mobile=mobile,
                address_line_1=address_line_1,
                address_line_2=address_line_2,
                city=city,
                state=state,
                postal_code=postal_code,
                country=country,
                notes=_text(
                    getattr(getattr(card, "note", None), "value", None),
                    10_000,
                    multiline=True,
                ),
            )
            if _has_identity(imported):
                contacts.append(imported)
            else:
                invalid += 1
        except Exception:
            invalid += 1

    return contacts, invalid


HEADER_ALIASES = {
    "first_name": {"firstname", "givenname", "first", "given"},
    "last_name": {"lastname", "familyname", "surname", "family"},
    "full_name": {"name", "fullname", "displayname"},
    "organization": {
        "company",
        "companyname",
        "organization",
        "organizationname",
        "business",
    },
    "job_title": {"jobtitle", "title", "position", "organizationtitle"},
    "email": {
        "email",
        "emailaddress",
        "email1value",
        "emailaddress1",
        "primaryemail",
    },
    "phone": {
        "phone",
        "telephone",
        "phonenumber",
        "phone1value",
        "businessphone",
        "homephone",
        "workphone",
    },
    "mobile": {"mobile", "mobilephone", "cell", "cellphone"},
    "address_line_1": {
        "address",
        "address1street",
        "address1formatted",
        "businessstreet",
        "street",
        "addressline1",
    },
    "address_line_2": {
        "address2",
        "address1line2",
        "address2street",
        "businessstreet2",
    },
    "city": {"city", "address1city", "businesscity"},
    "state": {"state", "region", "address1region", "businessstate"},
    "postal_code": {
        "zip",
        "zipcode",
        "postalcode",
        "address1postalcode",
        "businesspostalcode",
    },
    "country": {
        "country",
        "address1country",
        "businesscountry",
        "businesscountryregion",
    },
    "notes": {"notes", "note", "comments"},
}


def _normalize_header(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _map_csv_headers(fieldnames: list[str] | None) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for header in fieldnames or []:
        normalized = _normalize_header(header)
        for canonical, aliases in HEADER_ALIASES.items():
            if normalized in aliases and canonical not in mapping:
                mapping[canonical] = header
                break
    return mapping


def _csv_value(
    row: dict,
    mapping: dict[str, str],
    field: str,
    max_length: int | None = None,
    **kwargs,
):
    header = mapping.get(field)
    return _text(row.get(header), max_length, **kwargs) if header else None


def _first_export_value(value: str | None) -> str | None:
    """Google contact CSVs separate multiple values with ' ::: '."""
    if value and " ::: " in value:
        return value.split(" ::: ", 1)[0].strip()
    return value


def _csv_multi_value(
    row: dict, mapping: dict[str, str], field: str, max_length: int
) -> str | None:
    return _text(_first_export_value(_csv_value(row, mapping, field)), max_length)


def _parse_csv(text: str) -> tuple[list[ImportedContact], int]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    mapping = _map_csv_headers(reader.fieldnames)
    identity_fields = {
        "first_name",
        "last_name",
        "full_name",
        "organization",
        "email",
    }
    if not identity_fields.intersection(mapping):
        raise ContactImportError(
            "Could not recognize contact columns in the CSV. Export contacts "
            "as CSV from Google Contacts or Outlook and try again."
        )

    contacts: list[ImportedContact] = []
    invalid = 0
    for index, row in enumerate(reader):
        if index >= MAX_CONTACTS_PER_IMPORT:
            raise ContactImportError(
                f"Import at most {MAX_CONTACTS_PER_IMPORT:,} contacts at a time."
            )

        first_name = _csv_value(row, mapping, "first_name", 100)
        last_name = _csv_value(row, mapping, "last_name", 100)
        if not first_name and not last_name:
            first_name, last_name = _split_full_name(
                _csv_value(row, mapping, "full_name", 200)
            )

        imported = ImportedContact(
            first_name=first_name,
            last_name=last_name,
            organization=_csv_value(row, mapping, "organization", 200),
            job_title=_csv_value(row, mapping, "job_title", 150),
            email=_email(_first_export_value(_csv_value(row, mapping, "email"))),
            phone=_csv_multi_value(row, mapping, "phone", 50),
            mobile=_csv_multi_value(row, mapping, "mobile", 50),
            address_line_1=_csv_value(row, mapping, "address_line_1", 150),
            address_line_2=_csv_value(row, mapping, "address_line_2", 150),
            city=_csv_value(row, mapping, "city", 100),
            state=_csv_value(row, mapping, "state", 100),
            postal_code=_csv_value(row, mapping, "postal_code", 20),
            country=_csv_value(row, mapping, "country", 100),
            notes=_csv_value(row, mapping, "notes", 10_000, multiline=True),
        )
        if _has_identity(imported):
            contacts.append(imported)
        else:
            invalid += 1

    return contacts, invalid


def _split_quoted(value: str, separator: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    in_quotes = False
    escaped = False
    for character in value:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            current.append(character)
            escaped = True
        elif character == '"':
            in_quotes = not in_quotes
            current.append(character)
        elif character == separator and not in_quotes:
            parts.append("".join(current))
            current = []
        else:
            current.append(character)
    parts.append("".join(current))
    return parts


def _split_ics_property(line: str) -> tuple[str, str] | None:
    in_quotes = False
    escaped = False
    for index, character in enumerate(line):
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == '"':
            in_quotes = not in_quotes
        elif character == ":" and not in_quotes:
            return line[:index], line[index + 1 :]
    return None


def _unescape_ics(value: str) -> str:
    return (
        value.replace("\\n", "\n")
        .replace("\\N", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def _parse_ics(text: str) -> tuple[list[ImportedContact], int]:
    unfolded = re.sub(r"\r?\n[ \t]", "", text)
    contacts: list[ImportedContact] = []
    invalid = 0

    for line in unfolded.splitlines():
        if not line or ":" not in line:
            continue
        split = _split_ics_property(line)
        if split is None:
            continue
        left, raw_value = split
        segments = _split_quoted(left, ";")
        property_name = segments[0].upper()
        if property_name not in {"ATTENDEE", "ORGANIZER"}:
            continue

        params: dict[str, str] = {}
        for segment in segments[1:]:
            if "=" not in segment:
                continue
            key, value = segment.split("=", 1)
            params[key.upper()] = _unescape_ics(value.strip().strip('"'))

        email = _email(params.get("EMAIL") or raw_value)
        if not email:
            invalid += 1
            continue

        first_name, last_name = _name_from_cn(params.get("CN"))
        contacts.append(
            ImportedContact(
                first_name=first_name,
                last_name=last_name,
                email=email,
            )
        )

    return contacts, invalid


def parse_contact_file(filename: str | None, data: bytes) -> ImportResult:
    """Parse a vCard, CSV, or iCalendar export into normalized contacts."""
    if not data:
        raise ContactImportError("The uploaded file is empty.")
    if len(data) > MAX_IMPORT_BYTES:
        raise ContactImportError("Contact files must be 4 MB or smaller.")

    text = _decode(data)
    stripped = text.lstrip("\ufeff \t\r\n").upper()
    extension = Path(filename or "").suffix.lower()

    if stripped.startswith("BEGIN:VCARD"):
        source = "vcard"
        contacts, invalid = _parse_vcard(text)
    elif stripped.startswith("BEGIN:VCALENDAR"):
        source = "ics"
        contacts, invalid = _parse_ics(text)
    elif extension in {".vcf", ".vcard"}:
        raise ContactImportError("The uploaded .vcf file is not a valid vCard export.")
    elif extension == ".ics":
        raise ContactImportError(
            "The uploaded .ics file is not a valid iCalendar export."
        )
    else:
        source = "csv"
        contacts, invalid = _parse_csv(text)

    if len(contacts) > MAX_CONTACTS_PER_IMPORT:
        raise ContactImportError(
            f"Import at most {MAX_CONTACTS_PER_IMPORT:,} contacts at a time."
        )

    contacts, skipped = _deduplicate(contacts)
    if not contacts:
        if source == "ics":
            raise ContactImportError(
                "No attendee or organizer email addresses were found in the "
                "calendar file."
            )
        raise ContactImportError("No contacts could be read from that file.")

    return ImportResult(
        source=source,
        contacts=contacts,
        invalid=invalid,
        skipped_in_file=skipped,
    )
