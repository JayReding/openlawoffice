# Firm Settings and Branding

This document covers the firm-wide settings feature and its secure logo
pipeline. It is separate from `README.md` by project convention.

## Overview

The firm profile is stored in the `firms` table and accessed through
`get_firm()` in `openlawoffice/firm_service.py`. The current release uses one
firm, but the table has a normal primary key so a future multi-firm version can
add membership without removing a singleton constraint.

Administrators manage the profile at `/settings/firm`. Staff accounts cannot
view or change it.

## Fields

| Field | Required | Notes |
| --- | --- | --- |
| Firm name | Yes | Trimmed, up to 200 characters. |
| Address line 1 | No | Up to 120 characters. |
| Address line 2 | No | Up to 120 characters. |
| City | No | Up to 100 characters. |
| State | No | U.S. state, D.C., or territory code. |
| ZIP | No | Normalized to `12345` or `12345-6789`. |
| Telephone | No | Normalized to a 10-digit U.S. format, e.g. `(217) 555-0100`. |
| Firm email | No | Validated and lowercased. |
| Website | No | HTTP/HTTPS only; a bare domain is prefixed with `https://`. |
| Logo | No | See limits and processing below. |

New installations create the firm during administrator setup, using the
administrator's full name as the initial firm name. Existing installations
without a firm create and prefill it the first time an administrator opens
Firm Settings.

## Access control

- `/settings/firm` requires an authenticated administrator via
  `admin_required` in `openlawoffice/auth/decorators.py`.
- The Firm Settings navigation link is only shown to administrators.
- Non-admin requests receive the existing 403 page.
- All changes are protected by CSRF and recorded in `audit_events` as
  `firm.updated`.

## Getting Started checklist

The dashboard's **Review firm settings** item completes after the first
successful change to the firm profile or logo. The audit log is the source of
truth: simply opening the settings page, or submitting the form without
changing anything, does not complete the item. Later edits leave it complete.

## Logo validation and storage

Upload limits and validation:

- Accepted formats: PNG, JPEG, and WebP. SVG and animated images are rejected.
- Maximum upload: 2 MB.
- Minimum dimensions: 64 × 64 pixels.
- Maximum input pixels: 25,000,000.
- Stored maximum dimension: 1600 px on the longest side.
- The re-encoded output is limited to 2 MB, progressively reducing dimensions
  if necessary.

Processing (`openlawoffice/branding.py`):

1. Read at most the configured maximum plus one byte.
2. Ignore the client's filename, extension, and MIME type.
3. Decode with Pillow and reject invalid, oversized, animated, or unsupported
   images.
4. Apply EXIF orientation and fully load the image.
5. Re-encode a fresh image, which removes EXIF, text chunks, ICC profiles,
   appended payloads, and polyglot content.
6. Hash the stored bytes with SHA-256 and write them under a random filename.
7. Store files outside `static/` in `instance/uploads/firm/` by default.
8. Set the upload directory to `0700` and files to `0600`.

The original filename is never used for storage.

## Serving the logo

`GET /branding/logo` is public so the login page can display firm branding.
The route:

- Serves only the sanitized stored file, never a user-provided path or name.
- Uses the validated content type from the database.
- Sets `X-Content-Type-Options: nosniff`.
- Uses the content hash as an ETag and cache-busting query value.
- Allows public caching for one day.
- Returns 404 when no logo is configured.

## Configuration

Defaults live in `openlawoffice/config.py`:

| Setting | Default |
| --- | --- |
| `MAX_CONTENT_LENGTH` | 4 MB request cap |
| `FIRM_LOGO_UPLOAD_DIR` | `instance/uploads/firm` |
| `FIRM_LOGO_MAX_BYTES` | 2 MB |
| `FIRM_LOGO_MAX_DIMENSION` | 1600 px |
| `FIRM_LOGO_MIN_DIMENSION` | 64 px |
| `FIRM_LOGO_MAX_PIXELS` | 25,000,000 |

`FIRM_LOGO_UPLOAD_DIR` can also be set through the environment.

## Schema handling

The application now performs an additive `db.create_all()` during startup.
This lets an already-initialized installation gain the new `firms` table
without revisiting the first-run setup screen. Existing tables and columns are
not altered.

Before changing existing tables or adding formal migrations, replace this
startup bootstrap with Alembic/Flask-Migrate. Running `create_all()` before
autogenerating migrations can hide schema differences.

## Tests

`tests/test_firm_settings.py` covers:

- Creation of the firm during setup and on first visit for existing installs.
- Admin-only access, including POST attempts by staff.
- Field normalization and validation.
- Logo re-encoding, dimension reduction, metadata stripping, and public
  filename randomization.
- File and directory permissions.
- Public logo serving, caching headers, and ETags.
- Logo replacement and removal with old-file cleanup.
- Rejection of SVG, invalid images, oversized uploads, and excessive pixels.
- Audit events and startup schema creation.
