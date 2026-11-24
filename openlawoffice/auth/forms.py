"""Authentication forms."""

from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length

PASSWORD_MAX_LENGTH = 128


class LoginForm(FlaskForm):
    email = StringField(
        "Email address",
        validators=[DataRequired(), Email(), Length(max=255)],
        render_kw={
            "autocomplete": "username",
            "autofocus": True,
            "inputmode": "email",
            "spellcheck": "false",
        },
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(max=PASSWORD_MAX_LENGTH)],
        render_kw={"autocomplete": "current-password"},
    )
    remember = BooleanField("Keep me signed in on this device")
    submit = SubmitField("Sign in")
