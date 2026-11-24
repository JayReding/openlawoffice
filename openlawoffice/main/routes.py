"""Status and future application modules."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ..bootstrap import is_initialized
from ..extensions import db

bp = Blueprint("main", __name__)


@bp.get("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("auth.login"))


@bp.get("/dashboard")
@login_required
def dashboard():
    return render_template("main/dashboard.html")


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
