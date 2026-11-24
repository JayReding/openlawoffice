# Open Law Office

Open Law Office is a set of free and open-source tools for legal timekeeping,
billing, and basic CRM functions. It is intended to improve access to justice
in the United States by ensuring that basic practice management tools are
available to all under a permissive open source license.

## Current status: application skeleton

This release provides the secure foundation the rest of the application will
build on:

- A Flask application factory with blueprints and configuration via environment
  variables or `instance/config.py`.
- SQLAlchemy models with SQLite by default and a connection string abstraction
  for PostgreSQL and MariaDB/MySQL later.
- A first-run screen that creates the initial administrator account and then
  permanently closes setup.
- Secure sign-in with hashed passwords, CSRF protection, session rotation,
  per-account lockout after repeated failures, and an append-only audit trail.
- A placeholder dashboard, health check, CLI commands, and tests.

Matters, timekeeping, and billing screens are intentionally not implemented
yet. The navigation marks them as planned.

## Requirements

- Python 3.11 or newer
- A virtual environment

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

flask --app openlawoffice run --debug
```

Open <http://127.0.0.1:5000>. With no database present, the app redirects every
request to `/setup`. Create the administrator account there; you are signed in
and taken to the dashboard. Setup is then locked.

The app stores its SQLite database at `instance/openlawoffice.db` and generates
a persistent session secret at `instance/secret_key` (mode `0600`) if you do
not supply `SECRET_KEY`. Both are ignored by git.

## Configuration

Copy `.env.example` to `.env` for local development. Flask loads it
automatically when `python-dotenv` is installed.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_ENV` | `development` | Set to `production` to enable secure-cookie defaults and production warnings. |
| `SECRET_KEY` | generated file | Session and CSRF signing key. Set explicitly in managed deployments. |
| `DATABASE_URL` | SQLite in `instance/` | SQLAlchemy connection URL. |
| `SESSION_COOKIE_SECURE` | on in production | Send cookies only over HTTPS. |
| `SESSION_LIFETIME_HOURS` | `12` | Signed-in session lifetime. |
| `SETUP_TOKEN` | unset | Optional one-time token required on the initial setup screen. |
| `TRUSTED_HOSTS` | Flask default | Comma-separated allowed hostnames (useful behind a proxy). |
| `TRUST_PROXY_HOPS` | `0` | Number of trusted reverse proxies setting `X-Forwarded-*` headers. |
| `TIMEZONE` | `America/New_York` | Display timezone for timestamps. Stored values remain UTC. |
| `PASSWORD_MIN_LENGTH` | `12` | Minimum password length. |
| `LOGIN_MAX_ATTEMPTS` | `5` | Failed sign-ins before a temporary lockout. |
| `LOGIN_LOCKOUT_MINUTES` | `15` | Lockout duration. |

Settings can also live in `instance/config.py` as Python variables. Explicit
`create_app(...)` arguments override both, which is how the tests configure an
isolated database.

### Database backends

SQLite is the default and requires no extra driver. To use a server database,
install the matching extra and set `DATABASE_URL`:

```bash
pip install -e ".[postgres]"
export DATABASE_URL="postgresql+psycopg://olo:secret@localhost:5432/openlawoffice"

# or

pip install -e ".[mariadb]"
export DATABASE_URL="mysql+pymysql://olo:secret@localhost:3306/openlawoffice"
```

The models use portable SQLAlchemy types and UTC-normalized timestamps. No
SQLite-specific SQL is used in application code.

## First-run security

The setup screen intentionally works before authentication so a fresh install
can be configured. Before exposing a new instance to the internet, do one of
the following:

1. Set `SETUP_TOKEN` to a long random value before starting the app (the setup
   form will require it), or
2. Complete setup while the app is reachable only from localhost.

Once the first user exists, `/setup` redirects away and cannot create accounts.

## CLI commands

```bash
flask --app openlawoffice init-db          # create missing tables
flask --app openlawoffice create-admin     # add another administrator
flask --app openlawoffice reset-password   # reset a password / clear lockout
```

`create-admin` and `reset-password` prompt for credentials and apply the same
password policy as the web forms.

## Schema and migrations

On a fresh database, the setup screen calls `db.create_all()` so the first run
works without extra commands. Flask-Migrate is installed and initialized for
versioned changes as the schema grows:

```bash
flask --app openlawoffice db init
flask --app openlawoffice db migrate -m "Initial schema"
flask --app openlawoffice db upgrade
```

Because `create_all()` and Alembic can diverge, move to migrations before the
first production schema change.

## Tests

```bash
pytest
```

The suite covers first-run detection, administrator creation, setup lockout,
CSRF protection, password policy, sign-in success/failure, account lockout,
safe redirects, audit events, health checks, and security headers.

## Security notes

- Passwords are hashed with Werkzeug's default (scrypt) and never logged or
  stored in plain text.
- CSRF tokens protect every state-changing form, including sign-out.
- Sign-in rotates the session to prevent fixation.
- Failed sign-ins are audited and lock the account temporarily after the
  configured number of attempts.
- Responses include a restrictive Content Security Policy, `nosniff`,
  frame-denial, and referrer restrictions. Authenticated pages are `no-store`.
- Deploy behind HTTPS and set `SESSION_COOKIE_SECURE=true` (automatic when
  `APP_ENV=production`).
- The built-in Flask server is for development only. Use a production WSGI
  server, for example `gunicorn -w 4 wsgi:app`.

## License

GNU Affero General Public License, version 3 or later. See `LICENSE`.
