"""Authentication blueprint: sign in and sign out."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy import or_, select

from ..extensions import db
from ..models import User, record_event, utcnow
from ..security import (
    check_password_or_dummy,
    clear_failed_logins,
    is_locked,
    is_safe_redirect,
    register_failed_login,
)
from .forms import LoginForm

bp = Blueprint("auth", __name__)

GENERIC_LOGIN_ERROR = "Invalid username/email or password."


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        identifier = (form.identifier.data or "").strip().lower()
        password = form.password.data or ""
        user = db.session.scalar(
            select(User).where(
                or_(User.email == identifier, User.username == identifier)
            )
        )

        if user is not None and is_locked(user):
            record_event(
                "auth.login.blocked",
                detail={"reason": "locked", "identifier": identifier},
            )
            db.session.commit()
            flash(
                "This account is temporarily locked after too many failed "
                "sign-in attempts. Try again later.",
                "error",
            )
            return render_template("auth/login.html", form=form), 429

        if check_password_or_dummy(user, password) and user is not None and user.active:
            user.last_login_at = utcnow()
            clear_failed_logins(user)
            record_event("auth.login.succeeded", actor=user)
            db.session.commit()

            # Rotate the session on privilege change to prevent fixation.
            session.clear()
            login_user(user, remember=form.remember.data, fresh=True)
            session.permanent = True
            flash(f"Signed in as {user.full_name}.", "success")

            target = request.args.get("next")
            if is_safe_redirect(target):
                return redirect(target)
            return redirect(url_for("main.dashboard"))

        lockout_triggered = False
        if user is not None and user.active:
            lockout_triggered = register_failed_login(user)

        record_event(
            "auth.login.failed",
            actor=user,
            detail={
                "identifier": identifier,
                "reason": "unknown_account" if user is None else "bad_password",
            },
        )
        db.session.commit()

        if lockout_triggered:
            flash(
                "Too many failed attempts. This account is temporarily locked.",
                "error",
            )
        else:
            flash(GENERIC_LOGIN_ERROR, "error")

    return render_template("auth/login.html", form=form)


@bp.post("/logout")
def logout():
    if current_user.is_authenticated:
        record_event("auth.logout", actor=current_user)
        db.session.commit()
        logout_user()
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))
