"""Status, branding, and future application modules."""

from __future__ import annotations

from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    send_file,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from ..bootstrap import is_initialized
from ..branding import stored_logo_path
from ..extensions import db
from ..firm_service import get_firm, has_saved_firm_settings
from ..models import Matter

bp = Blueprint("main", __name__)


@bp.get("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("auth.login"))


@bp.get("/dashboard")
@login_required
def dashboard():
    matter_count = db.session.scalar(select(func.count(Matter.id))) or 0
    return render_template(
        "main/dashboard.html",
        firm_settings_reviewed=has_saved_firm_settings(),
        matter_count=matter_count,
    )


@bp.get("/branding/logo")
def firm_logo():
    """Serve the sanitized firm logo publicly for the login page and header."""
    firm = get_firm()
    if firm is None or not firm.has_logo:
        abort(404)

    path = stored_logo_path(firm.logo_stored_name)
    if path is None or not path.is_file():
        abort(404)

    extension = Path(firm.logo_stored_name).suffix
    response = send_file(
        path,
        mimetype=firm.logo_content_type,
        conditional=True,
        etag=firm.logo_sha256,
        max_age=86400,
    )
    response.headers["Cache-Control"] = "public, max-age=86400"
    response.headers["Content-Disposition"] = f'inline; filename="firm-logo{extension}"'
    return response


@bp.get("/healthz")
def healthz():
    """Liveness/readiness endpoint that never exposes credentials."""
    db_ok = True
    try:
        db.session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        db.session.rollback()
        db_ok = False
        current_app.logger.warning("Health check: database unavailable.", exc_info=True)

    payload = {
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "unavailable",
        "initialized": is_initialized() if db_ok else False,
    }
    return jsonify(payload), 200 if db_ok else 503
