# Users

This document covers user accounts, admin user management, and the legacy
database upgrade for the new profile fields. It is separate from `README.md` by
project convention.

## Profile fields

| Field | Required | Notes |
| --- | --- | --- |
| Username | Yes | 3-50 characters; lowercase letters, numbers, dots, underscores, or hyphens. Unique. |
| Full name | Yes | Up to 120 characters. |
| Email | Yes | Validated, lowercased, unique. |
| Telephone | No | Normalized to a 10-digit U.S. format. |
| Office | No | Up to 100 characters. |
| Role | No | Associate, Partner, Of Counsel, Attorney, Paralegal, or Staff. Defaults to Associate. |
| Department | No | Up to 100 characters. |

A password is required when an administrator creates an account, but is not a
profile field. Password changes use the reset-password workflow.

## Access level versus professional role

The existing access level remains separate from the new professional role:

- `users.role` — authorization level (`admin` or `member`).
- `users.professional_role` — the firm role shown in the UI: Associate, Partner,
  Of Counsel, Attorney, Paralegal, or Staff.

This keeps the current administrator/member authorization model intact while
leaving room for a future access-role and permissions system. Users created
through the admin UI are regular users, not administrators. Administrator
accounts are created by first-run setup or `flask create-admin`.

## Sign-in

The login field accepts either a username or an email address, case-insensitively.
Existing accounts can continue signing in with email.

## Admin user management

Administrators manage accounts at `/settings/users`.

- **List:** username, full name, email, telephone, role, office, department, and
  access level.
- **Create:** set all profile fields and an initial password.
- **Edit:** update profile details; usernames and emails remain unique.
- **Reset password:** set a new password and clear failed-login counters and
  lockouts.
- **Delete:** confirm through a warning screen before permanent deletion.

All routes use the administrator guard and CSRF protection.

## Deletion safeguards

- An administrator cannot delete their own account through the UI.
- The last administrator account cannot be deleted.
- Deleting a user does not delete firm history. Matters, audit events, and other
  records that reference the user have their attribution set to null through the
  existing foreign-key rules.
- The deletion warning explicitly explains that sign-in access is removed and
  attribution is cleared.

## Audit events

- `user.created`
- `user.updated`
- `user.password_reset`
- `user.deleted`

Audit details contain identifiers and changed field names, never passwords.

## Legacy database upgrade

The existing startup schema process creates new tables with
`db.create_all()`, which does not add columns to existing tables. This release
adds an idempotent user-column upgrade before the application serves requests:

1. Add missing `username`, `telephone`, `office`, `professional_role`, and
   `department` columns.
2. Default existing `professional_role` values to Associate.
3. Backfill usernames from the email local part, with numeric suffixes for
   collisions.
4. Add a unique username index.

The upgrade runs in `openlawoffice/schema_upgrades.py`. It is additive and safe
to rerun. As with the rest of the startup schema bootstrap, replace it with
Alembic/Flask-Migrate before introducing destructive or complex migrations.

## CLI

`flask create-admin` now prompts for a username first, followed by full name,
email, and password. The new administrator receives the Associate professional
role by default.

## Tests

`tests/test_users.py` covers:

- Admin user list access and member denial.
- Required-field creation and professional-role defaults.
- Normalization and duplicate validation.
- Editing profiles and auditing changes.
- Password resets, lockout clearing, and login with the new password.
- Deletion warning behavior, matter attribution cleanup, self-deletion guards,
  and audit events.
- Legacy database column addition and username backfill.
