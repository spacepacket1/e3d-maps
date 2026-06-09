from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from schemas._compat import CompatBaseModel
from schemas.shared_enums import is_known_signal_type


class StoryTypeDefinition(CompatBaseModel):
    story_type: str
    display_name: str
    category: str
    human_meaning: str
    agent_meaning: str
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    example_questions: list[str] = Field(default_factory=list)
    related_navigation_signal_types: list[str] = Field(default_factory=list)
    schema_version: str
    created_at: datetime
    updated_at: datetime

    @field_validator("related_navigation_signal_types", mode="after")
    @classmethod
    def validate_related_navigation_signal_types(cls, value: list[str]) -> list[str]:
        for item in value:
            if not is_known_signal_type(item):
                raise ValueError(f"Unknown signal type: {item}")
        return value

    @classmethod
    def model_validate(cls, obj, context=None):
        allow_unknown = bool((context or {}).get("allow_unknown_signal_types"))
        if not allow_unknown or not isinstance(obj, dict):
            return super().model_validate(obj, context=context)

        patched = dict(obj)
        related = []
        original = list(obj.get("related_navigation_signal_types", []))
        for item in original:
            related.append(item if is_known_signal_type(item) else "capital_migration")
        patched["related_navigation_signal_types"] = related
        model = super().model_validate(patched, context=context)
        model.related_navigation_signal_types = original
        return model
