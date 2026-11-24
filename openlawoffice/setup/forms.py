"""First-run administrator setup form."""

from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError

from ..security import normalize_email, password_policy_errors

PASSWORD_MAX_LENGTH = 128


class SetupForm(FlaskForm):
    full_name = StringField(
        "Full name",
        validators=[DataRequired(), Length(min=2, max=120)],
        render_kw={"autocomplete": "name", "autofocus": True},
    )
    email = StringField(
        "Email address",
        validators=[DataRequired(), Email(), Length(max=255)],
        render_kw={
            "autocomplete": "email",
            "inputmode": "email",
            "spellcheck": "false",
        },
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(max=PASSWORD_MAX_LENGTH)],
        render_kw={"autocomplete": "new-password"},
    )
    confirm_password = PasswordField(
        "Confirm password",
        validators=[
            DataRequired(),
            EqualTo("password", message="Passwords must match."),
        ],
        render_kw={"autocomplete": "new-password"},
    )
    setup_token = PasswordField(
        "Setup token",
        validators=[Length(max=255)],
        render_kw={"autocomplete": "off"},
    )
    submit = SubmitField("Create administrator account")

    def validate_email(self, field):
        field.data = normalize_email(field.data)

    def validate_password(self, field):
        errors = password_policy_errors(
            field.data or "",
            email=self.email.data or "",
            full_name=self.full_name.data or "",
        )
        if errors:
            raise ValidationError(" ".join(errors))
