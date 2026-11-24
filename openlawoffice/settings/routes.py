"""Firm-wide settings."""

from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..auth.decorators import admin_required
from ..branding import LogoValidationError, remove_logo_file, store_logo
from ..extensions import db
from ..firm_service import FIRM_UPDATED_ACTION, cache_firm, get_firm
from ..matter_seed import display_matter_type_name, normalize_matter_type_name
from ..matters.forms import MatterTypeForm
from ..models import Firm, Matter, MatterType, record_event, utcnow
from .forms import FirmSettingsForm

bp = Blueprint("settings", __name__, url_prefix="/settings")

FIRM_TEXT_FIELDS = (
    "name",
    "address_line_1",
    "address_line_2",
    "city",
    "state",
    "postal_code",
    "telephone",
    "email",
    "website",
)

LOGO_FIELDS = (
    "logo_stored_name",
    "logo_content_type",
    "logo_size_bytes",
    "logo_width",
    "logo_height",
    "logo_sha256",
    "logo_uploaded_at",
)


def _get_or_create_firm() -> Firm:
    firm = get_firm()
    if firm is None:
        firm = Firm(name=current_user.full_name.strip(), updated_by_id=current_user.id)
        db.session.add(firm)
        db.session.commit()
        cache_firm(firm)
    return firm


def _clear_logo(firm: Firm) -> None:
    for field in LOGO_FIELDS:
        setattr(firm, field, None)


def _render(page_firm: Firm, form: FirmSettingsForm, status: int = 200):
    return (
        render_template("settings/firm.html", form=form, firm=page_firm),
        status,
    )


@bp.route("/firm", methods=["GET", "POST"])
@admin_required
def firm():
    page_firm = _get_or_create_firm()
    form = (
        FirmSettingsForm(obj=page_firm)
        if request.method == "GET"
        else FirmSettingsForm()
    )

    if form.validate_on_submit():
        upload = form.logo.data
        has_upload = bool(upload and getattr(upload, "filename", ""))

        if has_upload and form.remove_logo.data:
            form.logo.errors.append("Choose either a new logo or removal, not both.")
            return _render(page_firm, form)

        new_logo = None
        if has_upload:
            try:
                new_logo = store_logo(upload)
            except LogoValidationError as exc:
                form.logo.errors.append(str(exc))
                return _render(page_firm, form)

        old_logo_name = page_firm.logo_stored_name
        changed_fields: list[str] = []

        for field_name in FIRM_TEXT_FIELDS:
            value = getattr(form, field_name).data or ""
            value = value.strip() if isinstance(value, str) else ""
            new_value = value or None
            if getattr(page_firm, field_name) != new_value:
                changed_fields.append(field_name)
            setattr(page_firm, field_name, new_value)

        logo_action = None
        if new_logo is not None:
            page_firm.logo_stored_name = new_logo.stored_name
            page_firm.logo_content_type = new_logo.content_type
            page_firm.logo_size_bytes = new_logo.size_bytes
            page_firm.logo_width = new_logo.width
            page_firm.logo_height = new_logo.height
            page_firm.logo_sha256 = new_logo.sha256
            page_firm.logo_uploaded_at = utcnow()
            logo_action = "updated"
        elif form.remove_logo.data and old_logo_name:
            _clear_logo(page_firm)
            logo_action = "removed"

        page_firm.updated_by_id = current_user.id
        page_firm.updated_at = utcnow()

        if changed_fields or logo_action:
            detail = {"fields": changed_fields}
            if logo_action:
                detail["logo"] = logo_action
            record_event(FIRM_UPDATED_ACTION, actor=current_user, detail=detail)

        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            if new_logo is not None:
                remove_logo_file(new_logo.stored_name)
            current_app.logger.exception("Saving firm settings failed")
            flash("Firm settings could not be saved. Please try again.", "error")
            return _render(page_firm, form, status=500)

        if old_logo_name and (new_logo is not None or logo_action == "removed"):
            remove_logo_file(old_logo_name)

        cache_firm(page_firm)
        if changed_fields or logo_action:
            flash("Firm settings saved.", "success")
        else:
            flash("No changes to save.", "info")
        return redirect(url_for("settings.firm"))

    return _render(page_firm, form)


@bp.route("/matter-types", methods=["GET", "POST"])
@admin_required
def matter_types():
    form = MatterTypeForm()

    if form.validate_on_submit():
        name = display_matter_type_name(form.name.data)
        matter_type = MatterType(
            name=name,
            normalized_name=normalize_matter_type_name(name),
            is_default=False,
            active=True,
            created_by_id=current_user.id,
        )
        db.session.add(matter_type)
        try:
            db.session.flush()
            record_event(
                "matter_type.created",
                actor=current_user,
                detail={"matter_type_id": matter_type.id, "name": matter_type.name},
            )
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            form.name.errors.append("That matter type already exists.")
        else:
            flash(f'Matter type "{matter_type.name}" added.', "success")
            return redirect(url_for("settings.matter_types"))

    types = db.session.scalars(
        select(MatterType).order_by(func.lower(MatterType.name))
    ).all()
    matter_counts = dict(
        db.session.execute(
            select(Matter.matter_type_id, func.count(Matter.id)).group_by(
                Matter.matter_type_id
            )
        ).all()
    )
    return render_template(
        "settings/matter_types.html",
        form=form,
        matter_types=types,
        matter_counts=matter_counts,
    )


@bp.post("/matter-types/<int:matter_type_id>/toggle")
@admin_required
def toggle_matter_type(matter_type_id: int):
    matter_type = db.get_or_404(MatterType, matter_type_id)

    if matter_type.active:
        active_count = (
            db.session.scalar(
                select(func.count())
                .select_from(MatterType)
                .where(MatterType.active.is_(True))
            )
            or 0
        )
        if active_count <= 1:
            flash("At least one matter type must remain active.", "error")
            return redirect(url_for("settings.matter_types"))

    matter_type.active = not matter_type.active
    action = (
        "matter_type.reactivated" if matter_type.active else "matter_type.deactivated"
    )
    record_event(
        action,
        actor=current_user,
        detail={"matter_type_id": matter_type.id, "name": matter_type.name},
    )
    db.session.commit()

    state = "reactivated" if matter_type.active else "deactivated"
    flash(f'Matter type "{matter_type.name}" {state}.', "success")
    return redirect(url_for("settings.matter_types"))
