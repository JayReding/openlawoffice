"""Administrator-only user management."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..auth.decorators import admin_required
from ..extensions import db
from ..models import (
    PROFESSIONAL_ROLE_DEFAULT,
    ROLE_ADMIN,
    ROLE_MEMBER,
    User,
    record_event,
)
from .forms import ResetPasswordForm, UserCreateForm, UserEditForm

bp = Blueprint("users", __name__, url_prefix="/settings/users")


def _optional(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _professional_role(value: str | None) -> str:
    return value or PROFESSIONAL_ROLE_DEFAULT


@bp.get("/", strict_slashes=False)
@admin_required
def index():
    users = db.session.scalars(
        select(User).order_by(func.lower(User.full_name), User.id)
    ).all()
    return render_template("users/index.html", users=users)


@bp.route("/new", methods=["GET", "POST"])
@admin_required
def create():
    form = UserCreateForm()

    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            full_name=form.full_name.data,
            email=form.email.data,
            telephone=_optional(form.telephone.data),
            office=_optional(form.office.data),
            professional_role=_professional_role(form.professional_role.data),
            department=_optional(form.department.data),
            role=ROLE_MEMBER,
            active=True,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        try:
            db.session.flush()
            record_event(
                "user.created",
                actor=current_user,
                detail={"user_id": user.id, "username": user.username},
            )
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            form.username.errors.append(
                "That username or email address is already in use."
            )
        except SQLAlchemyError:
            db.session.rollback()
            flash("The user could not be created. Please try again.", "error")
            return render_template("users/new.html", form=form), 500
        else:
            flash(f'User "{user.username}" created.', "success")
            return redirect(url_for("users.index"))

    return render_template("users/new.html", form=form)


@bp.route("/<int:user_id>/edit", methods=["GET", "POST"])
@admin_required
def edit(user_id: int):
    target = db.get_or_404(User, user_id)
    form = (
        UserEditForm(obj=target, user=target)
        if request.method == "GET"
        else UserEditForm(user=target)
    )

    if form.validate_on_submit():
        changed = []
        values = {
            "username": form.username.data,
            "full_name": form.full_name.data,
            "email": form.email.data,
            "telephone": _optional(form.telephone.data),
            "office": _optional(form.office.data),
            "professional_role": _professional_role(form.professional_role.data),
            "department": _optional(form.department.data),
        }
        for field_name, value in values.items():
            if getattr(target, field_name) != value:
                changed.append(field_name)
            setattr(target, field_name, value)

        try:
            if changed:
                record_event(
                    "user.updated",
                    actor=current_user,
                    detail={"user_id": target.id, "fields": changed},
                )
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            form.username.errors.append(
                "That username or email address is already in use."
            )
        except SQLAlchemyError:
            db.session.rollback()
            flash("The user could not be saved. Please try again.", "error")
            return render_template("users/edit.html", form=form, user=target), 500
        else:
            if changed:
                flash(f'User "{target.username}" updated.', "success")
            else:
                flash("No changes to save.", "info")
            return redirect(url_for("users.index"))

    return render_template("users/edit.html", form=form, user=target)


@bp.route("/<int:user_id>/reset-password", methods=["GET", "POST"])
@admin_required
def reset_password(user_id: int):
    target = db.get_or_404(User, user_id)
    form = ResetPasswordForm(user=target)

    if form.validate_on_submit():
        target.set_password(form.password.data)
        target.failed_login_count = 0
        target.locked_until = None
        record_event(
            "user.password_reset",
            actor=current_user,
            detail={"user_id": target.id, "username": target.username},
        )
        db.session.commit()
        flash(f'Password reset for "{target.username}".', "success")
        return redirect(url_for("users.index"))

    return render_template("users/reset_password.html", form=form, user=target)


@bp.route("/<int:user_id>/delete", methods=["GET", "POST"])
@admin_required
def delete(user_id: int):
    target = db.get_or_404(User, user_id)

    if target.id == current_user.id:
        flash("You cannot delete your own account.", "error")
        return redirect(url_for("users.index"))

    if target.is_admin:
        admin_count = (
            db.session.scalar(
                select(func.count()).select_from(User).where(User.role == ROLE_ADMIN)
            )
            or 0
        )
        if admin_count <= 1:
            flash("The last administrator account cannot be deleted.", "error")
            return redirect(url_for("users.index"))

    if request.method == "POST":
        detail = {
            "user_id": target.id,
            "username": target.username,
            "email": target.email,
        }
        record_event("user.deleted", actor=current_user, detail=detail)
        db.session.delete(target)
        db.session.commit()
        flash(f'User "{detail["username"]}" deleted.', "success")
        return redirect(url_for("users.index"))

    return render_template("users/delete.html", user=target)
