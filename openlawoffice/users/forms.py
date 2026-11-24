"""User management forms."""

from __future__ import annotations

from flask_wtf import FlaskForm
from sqlalchemy import select
from wtforms import PasswordField, SelectField, StringField, SubmitField
from wtforms.fields.choices import SelectChoice
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    Optional,
    ValidationError,
)

from ..extensions import db
from ..models import PROFESSIONAL_ROLE_DEFAULT, PROFESSIONAL_ROLES, User
from ..security import normalize_email, password_policy_errors
from ..validation import normalize_us_phone, normalize_username, username_error

PASSWORD_MAX_LENGTH = 128
ROLE_CHOICES = [SelectChoice("", "Select a role")] + [
    SelectChoice(role, role) for role in PROFESSIONAL_ROLES
]


def _strip(value: str | None) -> str:
    return value.strip() if isinstance(value, str) else ""


class UserDetailsForm(FlaskForm):
    username = StringField(
        "Username",
        filters=[normalize_username],
        validators=[DataRequired(), Length(min=3, max=50)],
        render_kw={"autocomplete": "off", "spellcheck": "false"},
    )
    full_name = StringField(
        "Full name",
        filters=[_strip],
        validators=[DataRequired(), Length(min=2, max=120)],
        render_kw={"autocomplete": "name"},
    )
    email = StringField(
        "Email address",
        filters=[_strip],
        validators=[DataRequired(), Email(), Length(max=255)],
        render_kw={"autocomplete": "email", "inputmode": "email"},
    )
    telephone = StringField(
        "Telephone",
        filters=[_strip],
        validators=[Optional(), Length(max=32)],
        render_kw={"autocomplete": "tel", "inputmode": "tel"},
    )
    office = StringField(
        "Office",
        filters=[_strip],
        validators=[Optional(), Length(max=100)],
    )
    professional_role = SelectField(
        "Role",
        choices=ROLE_CHOICES,
        validators=[Optional()],
        default=PROFESSIONAL_ROLE_DEFAULT,
    )
    department = StringField(
        "Department",
        filters=[_strip],
        validators=[Optional(), Length(max=100)],
    )

    def __init__(self, *args, user: User | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def validate_username(self, field):
        error = username_error(field.data)
        if error:
            raise ValidationError(error)
        query = select(User.id).where(User.username == field.data)
        if self.user is not None and self.user.id is not None:
            query = query.where(User.id != self.user.id)
        if db.session.scalar(query) is not None:
            raise ValidationError("That username is already in use.")

    def validate_email(self, field):
        field.data = normalize_email(field.data)
        query = select(User.id).where(User.email == field.data)
        if self.user is not None and self.user.id is not None:
            query = query.where(User.id != self.user.id)
        if db.session.scalar(query) is not None:
            raise ValidationError("That email address is already in use.")

    def validate_telephone(self, field):
        if not field.data:
            return
        try:
            field.data = normalize_us_phone(field.data)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc


class UserCreateForm(UserDetailsForm):
    password = PasswordField(
        "Initial password",
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
    submit = SubmitField("Create user")

    def validate_password(self, field):
        errors = password_policy_errors(
            field.data or "",
            email=self.email.data or "",
            full_name=self.full_name.data or "",
        )
        if errors:
            raise ValidationError(" ".join(errors))


class UserEditForm(UserDetailsForm):
    submit = SubmitField("Save changes")


class ResetPasswordForm(FlaskForm):
    password = PasswordField(
        "New password",
        validators=[DataRequired(), Length(max=PASSWORD_MAX_LENGTH)],
        render_kw={"autocomplete": "new-password", "autofocus": True},
    )
    confirm_password = PasswordField(
        "Confirm password",
        validators=[
            DataRequired(),
            EqualTo("password", message="Passwords must match."),
        ],
        render_kw={"autocomplete": "new-password"},
    )
    submit = SubmitField("Reset password")

    def __init__(self, *args, user: User | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def validate_password(self, field):
        user = self.user
        errors = password_policy_errors(
            field.data or "",
            email=user.email if user else "",
            full_name=user.full_name if user else "",
        )
        if errors:
            raise ValidationError(" ".join(errors))
