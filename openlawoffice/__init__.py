"""Open Law Office application factory."""

from __future__ import annotations

import os
import secrets
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask, redirect, render_template, request, url_for
from flask_wtf.csrf import CSRFError
from sqlalchemy.exc import SQLAlchemyError

from .config import default_config, engine_options
from .extensions import csrf, db, login_manager, migrate

# Routes that must remain reachable while the application is uninitialized.
SETUP_EXEMPT_ENDPOINTS = frozenset({"static", "setup.index", "main.healthz"})

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "style-src 'self'; "
    "script-src 'self'; "
    "object-src 'none'"
)


def _load_or_create_secret_key(app: Flask) -> str:
    """Read the persisted development key, creating it atomically if needed."""
    key_path = Path(app.instance_path) / "secret_key"
    key_path.parent.mkdir(parents=True, exist_ok=True)

    if key_path.exists():
        existing = key_path.read_text(encoding="utf-8").strip()
        if len(existing) >= 32:
            return existing

    new_key = secrets.token_urlsafe(48)
    try:
        descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        existing = key_path.read_text(encoding="utf-8").strip()
        if len(existing) >= 32:
            return existing
        key_path.write_text(new_key + "\n", encoding="utf-8")
        os.chmod(key_path, 0o600)
        app.logger.warning("Regenerated an invalid instance/secret_key file.")
        return new_key

    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(new_key + "\n")
    app.logger.info("Generated a new secret key at %s", key_path)
    return new_key


def _register_blueprints(app: Flask) -> None:
    from .auth import bp as auth_bp
    from .main import bp as main_bp
    from .matters import bp as matters_bp
    from .settings import bp as settings_bp
    from .setup import bp as setup_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(setup_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(matters_bp)
    app.register_blueprint(settings_bp)


def _register_request_hooks(app: Flask) -> None:
    from .bootstrap import is_initialized

    @app.before_request
    def require_setup():
        endpoint = request.endpoint or ""
        if endpoint in SETUP_EXEMPT_ENDPOINTS or endpoint.startswith("static."):
            return None
        if not is_initialized():
            return redirect(url_for("setup.index"))
        return None

    @app.after_request
    def apply_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)

        if request.is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )

        # Avoid caching authenticated pages or forms on shared machines.
        if request.endpoint != "static":
            response.headers.setdefault("Cache-Control", "no-store")
        return response


def _register_error_handlers(app: Flask) -> None:
    def render_error(code: int, heading: str, message: str):
        return (
            render_template(
                "errors/error.html", code=code, heading=heading, message=message
            ),
            code,
        )

    @app.errorhandler(404)
    def not_found(_error):
        return render_error(
            404,
            "Page not found",
            "The page you requested does not exist or has moved.",
        )

    @app.errorhandler(403)
    def forbidden(_error):
        return render_error(
            403,
            "Access denied",
            "You do not have permission to view this page.",
        )

    @app.errorhandler(413)
    def request_too_large(_error):
        return render_error(
            413, "Request too large", "The submitted request exceeded the size limit."
        )

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        return render_error(
            400,
            "Session expired",
            "Your form session expired or the security token was invalid. "
            "Go back, reload the page, and try again.",
        )

    @app.errorhandler(500)
    def internal_error(_error):
        db.session.rollback()
        app.logger.exception("Unhandled application error")
        return render_error(
            500,
            "Something went wrong",
            "An unexpected error occurred. The incident has been logged.",
        )


def _register_template_helpers(app: Flask) -> None:
    from .us_states import US_STATES

    timezone_name = app.config.get("TIMEZONE", "UTC")
    try:
        display_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:  # pragma: no cover - depends on host tzdata
        app.logger.warning("Unknown TIMEZONE %r; falling back to UTC.", timezone_name)
        display_timezone = ZoneInfo("UTC")

    state_names = dict(US_STATES)

    @app.template_filter("localtime")
    def format_localtime(
        value: datetime | None, fmt: str = "%b %d, %Y at %I:%M %p"
    ) -> str:
        if value is None:
            return "—"
        if value.tzinfo is None:
            return value.strftime(fmt)
        return value.astimezone(display_timezone).strftime(fmt).replace(" 0", " ")

    @app.context_processor
    def inject_globals():
        from .firm_service import get_firm

        return {
            "app_name": app.config["APP_NAME"],
            "current_year": datetime.now(display_timezone).year,
            "firm": get_firm(),
            "state_name": lambda code: state_names.get(code, code or "—"),
        }


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(app.instance_path, 0o700)
    except OSError:  # pragma: no cover - platform/filesystem dependent
        app.logger.warning("Could not restrict permissions on %s", app.instance_path)

    app.config.from_mapping(default_config(app.instance_path))
    # Optional deployment-specific settings: instance/config.py
    app.config.from_pyfile("config.py", silent=True)
    if test_config:
        app.config.update(test_config)

    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = _load_or_create_secret_key(app)
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = engine_options(
        app.config["SQLALCHEMY_DATABASE_URI"]
    )

    proxy_hops = app.config.get("TRUST_PROXY_HOPS", 0)
    if proxy_hops:
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=proxy_hops,
            x_proto=proxy_hops,
            x_host=proxy_hops,
            x_port=proxy_hops,
        )

    # Register models before any create_all() call.
    from . import models  # noqa: F401

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Additively create missing tables at startup so existing installations
    # gain new tables (such as firm-wide settings) without revisiting the
    # first-run setup screen. Existing tables and columns are untouched.
    from .bootstrap import ensure_schema
    from .matter_seed import seed_default_matter_types

    with app.app_context():
        try:
            ensure_schema()
            seed_default_matter_types()
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.warning(
                "Could not prepare the database schema at startup.",
                exc_info=True,
            )

    _register_blueprints(app)
    _register_request_hooks(app)
    _register_error_handlers(app)
    _register_template_helpers(app)

    from .cli import register_cli

    register_cli(app)

    if app.config.get("ENVIRONMENT") == "production" and not app.config.get(
        "SETUP_TOKEN"
    ):
        app.logger.warning(
            "SETUP_TOKEN is not configured. Set it before exposing a fresh "
            "instance to the internet so the first administrator cannot be "
            "claimed by someone else."
        )

    return app
