"""Operational CLI commands: flask init-db, create-admin, reset-password."""

from __future__ import annotations

import click
from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .bootstrap import ensure_schema
from .extensions import db
from .models import ROLE_ADMIN, User, record_event
from .security import normalize_email, password_policy_errors


def _validated_email(raw: str) -> str:
    try:
        result = validate_email(normalize_email(raw), check_deliverability=False)
    except EmailNotValidError as exc:
        raise click.ClickException(f"Invalid email address: {exc}") from exc
    return normalize_email(result.normalized)


def _validated_name(raw: str) -> str:
    name = " ".join(raw.split())
    if len(name) < 2 or len(name) > 120:
        raise click.ClickException("Enter a full name between 2 and 120 characters.")
    return name


@click.command("init-db")
def init_db_command() -> None:
    """Create any missing database tables."""
    try:
        ensure_schema()
    except SQLAlchemyError as exc:
        raise click.ClickException(f"Could not initialize the database: {exc}") from exc
    click.echo("Database schema is ready.")


@click.command("create-admin")
@click.option("--name", prompt="Full name")
@click.option("--email", prompt="Email address")
@click.password_option("--password", prompt="Password", confirmation_prompt=True)
def create_admin_command(email: str, name: str, password: str) -> None:
    """Create an additional administrator account."""
    try:
        ensure_schema()
    except SQLAlchemyError as exc:
        raise click.ClickException(f"Could not initialize the database: {exc}") from exc

    email = _validated_email(email)
    name = _validated_name(name)
    errors = password_policy_errors(password, email=email, full_name=name)
    if errors:
        raise click.ClickException(" ".join(errors))

    if db.session.scalar(select(User.id).where(User.email == email)) is not None:
        raise click.ClickException(f"An account with {email} already exists.")

    user = User(email=email, full_name=name, role=ROLE_ADMIN, active=True)
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.flush()
        record_event("admin.created", actor=user, detail={"email": user.email})
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise click.ClickException("That email address is already in use.") from exc
    click.echo(f"Administrator {user.email} created.")


@click.command("reset-password")
@click.option("--email", prompt="Email address")
@click.password_option("--password", prompt="New password", confirmation_prompt=True)
def reset_password_command(email: str, password: str) -> None:
    """Reset an account password and clear any login lockout."""
    email_normalized = _validated_email(email)
    try:
        user = db.session.scalar(select(User).where(User.email == email_normalized))
    except SQLAlchemyError as exc:
        db.session.rollback()
        raise click.ClickException(f"Could not query the database: {exc}") from exc
    if user is None:
        raise click.ClickException(f"No account found for {email_normalized}.")

    errors = password_policy_errors(
        password, email=user.email, full_name=user.full_name
    )
    if errors:
        raise click.ClickException(" ".join(errors))

    user.set_password(password)
    user.failed_login_count = 0
    user.locked_until = None
    try:
        record_event("account.password_reset", actor=user, detail={"email": user.email})
        db.session.commit()
    except SQLAlchemyError as exc:
        db.session.rollback()
        raise click.ClickException(f"Could not update the account: {exc}") from exc
    click.echo(f"Password reset for {user.email}.")


def register_cli(app) -> None:
    app.cli.add_command(init_db_command)
    app.cli.add_command(create_admin_command)
    app.cli.add_command(reset_password_command)
