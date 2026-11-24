"""Contact forms."""

from __future__ import annotations

from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms import StringField, SubmitField, TextAreaField
from wtforms.validators import Email, Length, Optional, ValidationError

from ..security import normalize_email


def _strip(value: str | None) -> str:
    return value.strip() if isinstance(value, str) else ""


class ContactForm(FlaskForm):
    first_name = StringField(
        "First name",
        filters=[_strip],
        validators=[Optional(), Length(max=100)],
        render_kw={"autocomplete": "given-name", "autofocus": True},
    )
    last_name = StringField(
        "Last name",
        filters=[_strip],
        validators=[Optional(), Length(max=100)],
        render_kw={"autocomplete": "family-name"},
    )
    organization = StringField(
        "Organization",
        filters=[_strip],
        validators=[Optional(), Length(max=200)],
        render_kw={"autocomplete": "organization"},
    )
    job_title = StringField(
        "Job title",
        filters=[_strip],
        validators=[Optional(), Length(max=150)],
        render_kw={"autocomplete": "organization-title"},
    )
    email = StringField(
        "Email address",
        filters=[_strip],
        validators=[Optional(), Email(), Length(max=255)],
        render_kw={"autocomplete": "email", "inputmode": "email"},
    )
    phone = StringField(
        "Phone",
        filters=[_strip],
        validators=[Optional(), Length(max=50)],
        render_kw={"autocomplete": "tel", "inputmode": "tel"},
    )
    mobile = StringField(
        "Mobile",
        filters=[_strip],
        validators=[Optional(), Length(max=50)],
        render_kw={"autocomplete": "tel-national", "inputmode": "tel"},
    )
    address_line_1 = StringField(
        "Address line 1",
        filters=[_strip],
        validators=[Optional(), Length(max=150)],
        render_kw={"autocomplete": "address-line1"},
    )
    address_line_2 = StringField(
        "Address line 2",
        filters=[_strip],
        validators=[Optional(), Length(max=150)],
        render_kw={"autocomplete": "address-line2"},
    )
    city = StringField(
        "City",
        filters=[_strip],
        validators=[Optional(), Length(max=100)],
        render_kw={"autocomplete": "address-level2"},
    )
    state = StringField(
        "State / region",
        filters=[_strip],
        validators=[Optional(), Length(max=100)],
        render_kw={"autocomplete": "address-level1"},
    )
    postal_code = StringField(
        "Postal code",
        filters=[_strip],
        validators=[Optional(), Length(max=20)],
        render_kw={"autocomplete": "postal-code"},
    )
    country = StringField(
        "Country",
        filters=[_strip],
        validators=[Optional(), Length(max=100)],
        render_kw={"autocomplete": "country-name"},
    )
    notes = TextAreaField(
        "Notes",
        filters=[_strip],
        validators=[Optional(), Length(max=10_000)],
        render_kw={"rows": 5},
    )
    submit = SubmitField("Save contact")

    def validate_email(self, field):
        field.data = normalize_email(field.data) or ""

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        if not (self.first_name.data or self.last_name.data or self.organization.data):
            self.first_name.errors.append(
                "Enter a first name, last name, or organization."
            )
            return False
        return True


class ContactImportForm(FlaskForm):
    file = FileField(
        "Contact file",
        render_kw={"accept": ".vcf,.vcard,.csv,.ics"},
    )
    submit = SubmitField("Import contacts")

    def validate_file(self, field):
        if field.data is None or not getattr(field.data, "filename", ""):
            raise ValidationError("Choose a contact or calendar export file.")
