"""Matter list, creation, and detail views."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from ..auth.decorators import admin_required
from ..extensions import db
from ..models import Matter, MatterType, record_event
from .forms import MatterForm

bp = Blueprint("matters", __name__, url_prefix="/matters")


@bp.get("/", strict_slashes=False)
@login_required
def index():
    matters = db.session.scalars(
        select(Matter).order_by(Matter.created_at.desc(), Matter.id.desc())
    ).all()
    return render_template("matters/index.html", matters=matters)


@bp.route("/new", methods=["GET", "POST"])
@admin_required
def create():
    form = MatterForm()

    if form.validate_on_submit():
        matter_type = db.session.get(MatterType, form.matter_type_id.data)
        if matter_type is None or not matter_type.active:
            form.matter_type_id.errors.append("Choose an active matter type.")
        else:
            matter = Matter(
                title=form.title.data,
                matter_type_id=matter_type.id,
                jurisdiction=form.jurisdiction.data,
                description=form.description.data or None,
                created_by_id=current_user.id,
            )
            db.session.add(matter)
            db.session.flush()
            record_event(
                "matter.created",
                actor=current_user,
                detail={
                    "matter_id": matter.id,
                    "matter_type": matter_type.name,
                    "jurisdiction": matter.jurisdiction,
                },
            )
            db.session.commit()
            flash(f'Matter "{matter.title}" created.', "success")
            return redirect(url_for("matters.detail", matter_id=matter.id))

    return render_template("matters/new.html", form=form)


@bp.get("/<int:matter_id>")
@login_required
def detail(matter_id: int):
    matter = db.get_or_404(Matter, matter_id)
    return render_template("matters/detail.html", matter=matter)
