# Contacts

This document covers the Contacts section and file-based import behavior. It is
separate from `README.md` by project convention.

## Scope

Included:

- Contact list, search, and pagination.
- Manual contact creation, detail, editing, and deletion.
- File-based imports from vCard, CSV, and calendar exports.
- Audit events for contact changes and imports.

Not included yet:

- Linking contacts to matters.
- Multiple email addresses or phone numbers per contact.
- Contact categories, tags, or custom fields.
- Live synchronization with external providers.
- Duplicate merging tools.

## Fields

| Field | Required | Notes |
| --- | --- | --- |
| First name | No | At least one of first name, last name, or organization is required. |
| Last name | No | |
| Organization | No | At least one of first name, last name, or organization is required. |
| Job title | No | |
| Email | No | Validated and lowercased. |
| Phone | No | Kept as entered, up to 50 characters. |
| Mobile | No | Kept as entered, up to 50 characters. |
| Address lines 1-2 | No | |
| City | No | |
| State / region | No | Free text rather than a U.S.-only dropdown. |
| Postal code | No | |
| Country | No | |
| Notes | No | Up to 10,000 characters. |

Contacts also track their source: Manual, vCard, CSV, or Calendar, plus the
creating user and timestamps.

## Permissions

All signed-in users can view, create, edit, import, and delete contacts.

Deletion uses a warning screen before the record is permanently removed.

## Imports

Imports are file-based only. Files are parsed in memory and are not written to
disk.

Supported files:

### vCard (`.vcf`)

- Apple Contacts exports.
- Google Contacts exports.
- Outlook contact exports.
- Parsed with the `vobject` library.

Imported fields include name, organization, job title, email, work/cell phone,
address, and notes.

### CSV (`.csv`)

Recognizes standard Google Contacts and Outlook CSV headers, plus common
generic variants. Examples:

- Google: `Name`, `Given Name`, `Family Name`, `Organization Name`,
  `Organization Title`, `E-mail 1 - Value`, `Phone 1 - Value`,
  `Address 1 - Street`, and related address columns.
- Outlook: `First Name`, `Last Name`, `Company`, `Job Title`,
  `E-mail Address`, `Business Phone`, `Mobile Phone`, `Business Street`, and
  related columns.

### Calendar (`.ics`)

- Google, Apple, and Outlook calendar exports.
- Imports the email addresses and display names of event organizers and
  attendees.
- Events themselves are not imported.

## Import limits and duplicate handling

- Maximum file size: 4 MB.
- Maximum contacts per file: 5,000.
- Email addresses are validated and lowercased.
- Contacts with a matching email address already in the database are skipped.
- Contacts without an email address are also skipped when an existing contact
  has the same name and organization.
- Duplicates within a file are skipped by email, or by name and organization
  when no email is present.
- Invalid entries are skipped and counted in the import summary.
- If no contacts can be read, the import is rejected with an explanation.

Import summaries report created, duplicate, and invalid counts. A successful
import is recorded as `contact.imported`.

## Routes

| Route | Access | Purpose |
| --- | --- | --- |
| `/contacts` | Signed in | Contact list, search, and pagination |
| `/contacts/new` | Signed in | Create a contact |
| `/contacts/<id>` | Signed in | Contact detail |
| `/contacts/<id>/edit` | Signed in | Edit a contact |
| `/contacts/<id>/delete` | Signed in | Warning page and permanent deletion |
| `/contacts/import` | Signed in | Upload a contact or calendar export |

## Audit events

- `contact.created`
- `contact.updated`
- `contact.deleted`
- `contact.imported`

Import details include source, created count, duplicate count, and invalid
count. Contact details are not copied into the audit log.

## Tests

`tests/test_contacts.py` covers:

- Authentication and member access.
- Contact creation, required identity, normalization, editing, search, and
  pagination.
- Deletion warning and permanent deletion.
- vCard, Google CSV, Outlook CSV, and calendar attendee imports.
- Duplicate skipping and invalid-file handling.
- Source tracking and audit events.
