"""Matter forms."""

from __future__ import annotations

from flask_wtf import FlaskForm
from sqlalchemy import func, select
from wtforms import SelectField, StringField, SubmitField, TextAreaField
from wtforms.fields.choices import SelectChoice
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from ..extensions import db
from ..matter_seed import normalize_matter_type_name
from ..models import MatterType
from ..us_states import US_STATES

JURISDICTION_CHOICES = [SelectChoice("", "Select a jurisdiction")] + [
    SelectChoice(code, label) for code, label in US_STATES
]


def _strip(value: str | None) -> str:
    return value.strip() if isinstance(value, str) else ""


class MatterForm(FlaskForm):
    title = StringField(
        "Matter title",
        filters=[_strip],
        validators=[DataRequired(), Length(max=200)],
        render_kw={"autofocus": True, "autocomplete": "off"},
    )
    matter_type_id = SelectField(
        "Matter type",
        coerce=int,
        validators=[DataRequired(message="Choose a matter type.")],
    )
    jurisdiction = SelectField(
        "Jurisdiction",
        choices=JURISDICTION_CHOICES,
        validators=[DataRequired(message="Choose a jurisdiction.")],
    )
    description = TextAreaField(
        "Matter description",
        filters=[_strip],
        validators=[Optional(), Length(max=10_000)],
        render_kw={
            "rows": 8,
            "placeholder": "Facts, scope, goals, or other context for this matter.",
        },
    )
    submit = SubmitField("Create matter")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        types = db.session.scalars(
            select(MatterType)
            .where(MatterType.active.is_(True))
            .order_by(func.lower(MatterType.name))
        ).all()
        self.matter_type_id.choices = [SelectChoice("0", "Select a matter type")] + [
            SelectChoice(str(matter_type.id), matter_type.name) for matter_type in types
        ]

    @property
    def has_active_types(self) -> bool:
        return len(self.matter_type_id.choices) > 1


class MatterTypeForm(FlaskForm):
    name = StringField(
        "Matter type name",
        filters=[_strip],
        validators=[DataRequired(), Length(max=100)],
        render_kw={"autocomplete": "off"},
    )
    submit = SubmitField("Add matter type")

    def validate_name(self, field):
        normalized = normalize_matter_type_name(field.data)
        existing = db.session.scalar(
            select(MatterType).where(MatterType.normalized_name == normalized)
        )
        if existing is not None:
            if existing.active:
                raise ValidationError("That matter type already exists.")
            raise ValidationError(
                "That matter type already exists but is inactive. "
                "Reactivate it below instead."
            )
