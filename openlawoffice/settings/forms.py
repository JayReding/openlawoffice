"""Firm settings form and validation."""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms import BooleanField, SelectField, StringField, SubmitField
from wtforms.fields.choices import SelectChoice
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError

from ..security import normalize_email
from ..us_states import US_STATES
from ..validation import normalize_postal_code, normalize_us_phone

US_STATE_CHOICES = [SelectChoice("", "Select a state")] + [
    SelectChoice(code, label) for code, label in US_STATES
]


def _strip(value: str | None) -> str:
    return value.strip() if isinstance(value, str) else ""


class FirmSettingsForm(FlaskForm):
    name = StringField(
        "Firm name",
        filters=[_strip],
        validators=[DataRequired(), Length(max=200)],
        render_kw={"autocomplete": "organization", "autofocus": True},
    )
    address_line_1 = StringField(
        "Address line 1",
        filters=[_strip],
        validators=[Optional(), Length(max=120)],
        render_kw={"autocomplete": "address-line1"},
    )
    address_line_2 = StringField(
        "Address line 2",
        filters=[_strip],
        validators=[Optional(), Length(max=120)],
        render_kw={"autocomplete": "address-line2"},
    )
    city = StringField(
        "City",
        filters=[_strip],
        validators=[Optional(), Length(max=100)],
        render_kw={"autocomplete": "address-level2"},
    )
    state = SelectField(
        "State",
        choices=US_STATE_CHOICES,
        validators=[Optional()],
        render_kw={"autocomplete": "address-level1"},
    )
    postal_code = StringField(
        "ZIP code",
        filters=[_strip],
        validators=[Optional(), Length(max=10)],
        render_kw={"autocomplete": "postal-code", "inputmode": "numeric"},
    )
    telephone = StringField(
        "Telephone",
        filters=[_strip],
        validators=[Optional(), Length(max=32)],
        render_kw={"autocomplete": "tel", "inputmode": "tel"},
    )
    email = StringField(
        "Firm email",
        filters=[_strip],
        validators=[Optional(), Email(), Length(max=255)],
        render_kw={"autocomplete": "email", "inputmode": "email"},
    )
    website = StringField(
        "Website",
        filters=[_strip],
        validators=[Optional(), Length(max=255)],
        render_kw={"autocomplete": "url", "inputmode": "url"},
    )
    logo = FileField(
        "Logo file",
        render_kw={"accept": "image/png,image/jpeg,image/webp"},
    )
    remove_logo = BooleanField("Remove the current logo")
    submit = SubmitField("Save firm settings")

    def validate_postal_code(self, field):
        if not field.data:
            return
        try:
            field.data = normalize_postal_code(field.data)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    def validate_telephone(self, field):
        if not field.data:
            return
        try:
            field.data = normalize_us_phone(field.data)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    def validate_email(self, field):
        field.data = normalize_email(field.data) or ""

    def validate_website(self, field):
        value = field.data or ""
        if not value:
            return
        if any(char.isspace() for char in value) or any(
            ord(char) < 32 or ord(char) == 127 for char in value
        ):
            raise ValidationError("Enter a valid website address.")

        if "://" not in value:
            if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value):
                raise ValidationError("Website addresses must use HTTP or HTTPS.")
            value = f"https://{value}"

        try:
            parsed = urlsplit(value)
        except ValueError as exc:
            raise ValidationError("Enter a valid website address.") from exc

        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise ValidationError("Website addresses must use HTTP or HTTPS.")
        if parsed.username or parsed.password:
            raise ValidationError("Website addresses cannot include credentials.")
        try:
            _ = parsed.port
        except ValueError as exc:
            raise ValidationError("Enter a valid website address.") from exc

        field.data = urlunsplit(
            (
                parsed.scheme.lower(),
                parsed.netloc,
                parsed.path,
                parsed.query,
                parsed.fragment,
            )
        )
