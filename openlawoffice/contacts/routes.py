"""Contact list, creation, detail, editing, deletion, and imports."""

from __future__ import annotations

from dataclasses import asdict

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..models import Contact, record_event
from .forms import ContactForm, ContactImportForm
from .importers import MAX_IMPORT_BYTES, ContactImportError, parse_contact_file

bp = Blueprint("contacts", __name__, url_prefix="/contacts")

CONTACT_FIELDS = (
    "first_name",
    "last_name",
    "organization",
    "job_title",
    "email",
    "phone",
    "mobile",
    "address_line_1",
    "address_line_2",
    "city",
    "state",
    "postal_code",
    "country",
    "notes",
)
PER_PAGE = 40
SOURCE_LABELS = {"vcard": "vCard", "csv": "CSV", "ics": "calendar"}


def _values(form: ContactForm) -> dict[str, str | None]:
    values = {}
    for field_name in CONTACT_FIELDS:
        value = getattr(form, field_name).data or ""
        values[field_name] = value.strip() if isinstance(value, str) else None
        if not values[field_name]:
            values[field_name] = None
    return values


def _apply(contact: Contact, form: ContactForm) -> list[str]:
    changed = []
    for field_name, value in _values(form).items():
        if getattr(contact, field_name) != value:
            changed.append(field_name)
        setattr(contact, field_name, value)
    return changed


@bp.get("/", strict_slashes=False)
@login_required
def index():
    query_text = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)

    query = select(Contact)
    if query_text:
        pattern = f"%{query_text.lower()}%"
        query = query.where(
            or_(
                func.lower(Contact.first_name).like(pattern),
                func.lower(Contact.last_name).like(pattern),
                func.lower(Contact.organization).like(pattern),
                func.lower(Contact.email).like(pattern),
                func.lower(Contact.phone).like(pattern),
                func.lower(Contact.mobile).like(pattern),
            )
        )
    query = query.order_by(
        func.coalesce(
            func.lower(Contact.last_name),
            func.lower(Contact.organization),
            "",
        ),
        func.coalesce(func.lower(Contact.first_name), ""),
        func.coalesce(func.lower(Contact.organization), ""),
        Contact.id,
    )
    pagination = db.paginate(query, page=page, per_page=PER_PAGE, error_out=False)
    return render_template(
        "contacts/index.html",
        contacts=pagination.items,
        pagination=pagination,
        query=query_text,
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    form = ContactForm()
    if form.validate_on_submit():
        contact = Contact(
            **_values(form), source="manual", created_by_id=current_user.id
        )
        db.session.add(contact)
        db.session.flush()
        record_event(
            "contact.created",
            actor=current_user,
            detail={"contact_id": contact.id, "name": contact.display_name},
        )
        db.session.commit()
        flash(f'Contact "{contact.display_name}" created.', "success")
        return redirect(url_for("contacts.detail", contact_id=contact.id))
    return render_template("contacts/form.html", form=form, contact=None)


@bp.get("/<int:contact_id>")
@login_required
def detail(contact_id: int):
    contact = db.get_or_404(Contact, contact_id)
    return render_template("contacts/detail.html", contact=contact)


@bp.route("/<int:contact_id>/edit", methods=["GET", "POST"])
@login_required
def edit(contact_id: int):
    contact = db.get_or_404(Contact, contact_id)
    form = ContactForm(obj=contact) if request.method == "GET" else ContactForm()
    if form.validate_on_submit():
        changed = _apply(contact, form)
        if changed:
            record_event(
                "contact.updated",
                actor=current_user,
                detail={"contact_id": contact.id, "fields": changed},
            )
        db.session.commit()
        if changed:
            flash(f'Contact "{contact.display_name}" updated.', "success")
        else:
            flash("No changes to save.", "info")
        return redirect(url_for("contacts.detail", contact_id=contact.id))
    return render_template("contacts/form.html", form=form, contact=contact)


@bp.route("/<int:contact_id>/delete", methods=["GET", "POST"])
@login_required
def delete(contact_id: int):
    contact = db.get_or_404(Contact, contact_id)
    if request.method == "POST":
        name = contact.display_name
        record_event(
            "contact.deleted",
            actor=current_user,
            detail={"contact_id": contact.id, "name": name},
        )
        db.session.delete(contact)
        db.session.commit()
        flash(f'Contact "{name}" deleted.', "success")
        return redirect(url_for("contacts.index"))
    return render_template("contacts/delete.html", contact=contact)


@bp.route("/import", methods=["GET", "POST"])
@login_required
def import_contacts():
    form = ContactImportForm()
    if form.validate_on_submit():
        upload = form.file.data
        data = upload.read(MAX_IMPORT_BYTES + 1)
        try:
            result = parse_contact_file(upload.filename, data)
        except ContactImportError as exc:
            form.file.errors.append(str(exc))
        else:
            existing_emails = {
                email
                for email in db.session.scalars(
                    select(Contact.email).where(Contact.email.is_not(None))
                )
                if email
            }
            existing_name_keys = set()
            for first_name, last_name, organization in db.session.execute(
                select(
                    Contact.first_name,
                    Contact.last_name,
                    Contact.organization,
                ).where(Contact.email.is_(None))
            ):
                name_key = (
                    " ".join(
                        part for part in (first_name, last_name) if part
                    ).casefold(),
                    (organization or "").casefold(),
                )
                if name_key != ("", ""):
                    existing_name_keys.add(name_key)

            created = 0
            duplicates = 0
            for imported in result.contacts:
                if imported.email:
                    if imported.email in existing_emails:
                        duplicates += 1
                        continue
                else:
                    name_key = (
                        imported.full_name.casefold(),
                        (imported.organization or "").casefold(),
                    )
                    if name_key != ("", "") and name_key in existing_name_keys:
                        duplicates += 1
                        continue
                    existing_name_keys.add(name_key)

                contact = Contact(
                    **asdict(imported),
                    source=result.source,
                    created_by_id=current_user.id,
                )
                db.session.add(contact)
                created += 1
                if imported.email:
                    existing_emails.add(imported.email)

            try:
                if created:
                    record_event(
                        "contact.imported",
                        actor=current_user,
                        detail={
                            "source": result.source,
                            "created": created,
                            "duplicates": duplicates + result.skipped_in_file,
                            "invalid": result.invalid,
                        },
                    )
                    db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                flash("The contacts could not be imported. Please try again.", "error")
                return render_template("contacts/import.html", form=form), 500

            skipped = duplicates + result.skipped_in_file
            invalid = result.invalid
            if created:
                message = f"Imported {created} contact"
                message += "" if created == 1 else "s"
                message += f" from {SOURCE_LABELS.get(result.source, result.source)}."
                if skipped:
                    message += f" Skipped {skipped} duplicate"
                    message += "" if skipped == 1 else "s"
                    message += "."
                if invalid:
                    message += f" Skipped {invalid} invalid entr"
                    message += "y." if invalid == 1 else "ies."
                flash(message, "success")
            else:
                flash(
                    "No new contacts were imported. All readable contacts "
                    "already exist.",
                    "info",
                )
            return redirect(url_for("contacts.index"))

    return render_template("contacts/import.html", form=form)
