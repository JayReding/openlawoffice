"""One-time first-run administrator setup."""

from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    session,
    url_for,
)
from flask_login import current_user, login_user
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..bootstrap import database_label, ensure_schema, is_initialized, mark_initialized
from ..extensions import db
from ..models import ROLE_ADMIN, User, record_event, utcnow
from ..security import secure_compare
from .forms import SetupForm

bp = Blueprint("setup", __name__)

DATABASE_ERROR_MESSAGE = (
    "Open Law Office could not reach or prepare the configured database. "
    "Check DATABASE_URL and confirm the database server is running, then retry."
)


def _render_setup(form, *, db_error=None):
    return render_template(
        "setup/index.html",
        form=form,
        database=database_label(),
        db_error=db_error,
        show_setup_token=bool(current_app.config.get("SETUP_TOKEN")),
    )


@bp.route("/setup", methods=["GET", "POST"])
def index():
    if is_initialized():
        if current_user.is_authenticated:
            return redirect(url_for("main.dashboard"))
        return redirect(url_for("auth.login"))

    form = SetupForm()

    try:
        ensure_schema()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Database schema bootstrap failed")
        return _render_setup(form, db_error=DATABASE_ERROR_MESSAGE), 503

    if form.validate_on_submit():
        expected_token = current_app.config.get("SETUP_TOKEN")
        if expected_token and not secure_compare(
            form.setup_token.data or "", expected_token
        ):
            form.setup_token.errors.append("Incorrect setup token.")

        if not form.setup_token.errors:
            user = User(
                email=form.email.data,
                full_name=form.full_name.data.strip(),
                role=ROLE_ADMIN,
                active=True,
            )
            user.set_password(form.password.data)
            user.last_login_at = utcnow()
            db.session.add(user)

            try:
                db.session.flush()
                record_event(
                    "setup.completed", actor=user, detail={"email": user.email}
                )
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                form.email.errors.append("An account with that email already exists.")
            except SQLAlchemyError:
                db.session.rollback()
                current_app.logger.exception(
                    "Creating the initial administrator failed"
                )
                return _render_setup(form, db_error=DATABASE_ERROR_MESSAGE), 503
            else:
                mark_initialized()
                login_user(user, fresh=True)
                session.permanent = True
                flash(
                    "Administrator account created. Welcome to Open Law Office.",
                    "success",
                )
                return redirect(url_for("main.dashboard"))

    return _render_setup(form)
