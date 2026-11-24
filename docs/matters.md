# Matters

This document covers the first matters slice: matter types, matters, and the
jurisdiction list. It is separate from `README.md` by project convention.

## Scope

Included:

- Matter types with 33 seeded defaults and admin-managed custom types.
- Matter list, creation, and detail pages.
- U.S. state, D.C., and territory jurisdiction selection.
- Optional matter description.
- Dashboard matter count and first-matter checklist state.
- Audit events for matter and matter type changes.

Not included yet:

- Matter editing.
- Clients and contacts.
- Matter numbers and statuses.
- Assignments, rates, time entries, and billing links.
- Federal or non-U.S. jurisdictions. Jurisdiction is intentionally limited to
  states, D.C., and territories for now.

## Data model

### `matter_types`

- `name` — display name, up to 100 characters.
- `normalized_name` — whitespace-collapsed and casefolded, unique.
- `is_default` — identifies seeded built-in types.
- `active` — inactive types are hidden from new matter forms.
- `created_by_id` — nullable for seeded defaults.
- timestamps.

### `matters`

- `title` — required, up to 200 characters.
- `matter_type_id` — required foreign key.
- `jurisdiction` — required two-letter state/territory code.
- `description` — optional, up to 10,000 characters.
- `created_by_id` — nullable if the creating account is later removed.
- timestamps.

## Default matter types

The defaults are defined in `openlawoffice/matter_seed.py` and seeded
idempotently during app startup:

Appellate, Bankruptcy, Business Formation, Business Litigation, Civil,
Corporate, Consumer Protection, Criminal, Debtor/Creditor, Education, Elder Law,
Employment, ERISA, Estate Planning, Family Law, General Litigation, General
Practice, Government and Elections, Guardianship, Immigration, Insurance,
Intellectual Property, Long-Term Care, Military, Minerals, Oil, and Gas,
Personal Injury, Probate, Real Estate, Real Estate Litigation, Social Security,
Tax, Unemployment, Workers Compensation.

Seeding inserts only missing normalized names. A unique index plus a retry after
integrity errors prevents duplicates across restarts and concurrent workers.

## Permissions

- All signed-in users can view the matter list, create matters, and view matter
  details.
- Only administrators can manage matter types at `/settings/matter-types`.
- Matter type creation uses the same admin guard as firm settings.

## Matter type management

Administrators can:

- Add custom types.
- Deactivate and reactivate any type, including built-in types.
- See how many matters use each type.

Rules:

- Duplicate names are rejected case-insensitively after whitespace normalization.
- A duplicate of an inactive type must be reactivated rather than recreated.
- At least one type must remain active.
- Types are never deleted, so existing matters always retain a valid type.
- Inactive types remain visible on existing matters and are labeled as inactive.

## Matter form

`GET/POST /matters/new`

- Matter title — required.
- Matter type — required dropdown of active types.
- Jurisdiction — required dropdown of the 50 states, D.C., and territories.
- Description — optional multiline field, maximum 10,000 characters.

The description is displayed on the detail page with line breaks preserved and
normal HTML escaping.

## Routes

| Route | Access | Purpose |
| --- | --- | --- |
| `/matters` | Signed in | Matter list |
| `/matters/new` | Signed in | Create a matter |
| `/matters/<id>` | Signed in | Matter detail |
| `/settings/matter-types` | Administrator | List and add matter types |
| `/settings/matter-types/<id>/toggle` | Administrator | Deactivate/reactivate |

## Dashboard integration

- The Matters stat card shows the current matter count and links to the list.
- The “Add your first matter” checklist item is marked complete when at least
  one matter exists.

## Audit events

- `matter.created`
- `matter_type.created`
- `matter_type.deactivated`
- `matter_type.reactivated`

Audit details include identifiers and names, not matter descriptions.

## Schema and tests

New tables are created by the existing additive startup schema bootstrap, and
default types are seeded immediately afterward. No existing table columns are
changed.

`tests/test_matters.py` covers:

- Exact default seeding and idempotence.
- Admin-only type management.
- Custom type creation and duplicate normalization.
- Inactive type behavior and last-active-type protection.
- Matter creation, optional descriptions, validation, list, and detail.
- Member access to matters but not type management.
- Audit events and dashboard checklist updates.
