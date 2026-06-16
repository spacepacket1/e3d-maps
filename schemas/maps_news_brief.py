from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, StringConstraints, field_validator
from typing_extensions import Annotated

from schemas._compat import CompatBaseModel

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
HeadlineString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]
SummaryString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=420)
]
MapsNewsStance = Literal["risk_on", "risk_off", "neutral", "cautious", "crowded"]


class MapsNewsBrief(CompatBaseModel):
    id: NonEmptyString
    scope: NonEmptyString = "global"
    headline: HeadlineString
    summary: SummaryString
    stance: MapsNewsStance
    supporting_signal_ids: list[NonEmptyString] = Field(default_factory=list, max_length=8)
    supporting_story_ids: list[NonEmptyString] = Field(default_factory=list)
    supporting_thesis_ids: list[NonEmptyString] = Field(default_factory=list)
    tags: list[NonEmptyString] = Field(default_factory=list, max_length=6)
    created_by_agent: NonEmptyString = "maps_news_agent"
    model: str = ""
    adapter: str = ""
    schema_version: str = ""
    created_at: datetime

    @field_validator("headline")
    @classmethod
    def validate_headline(cls, value: str) -> str:
        if "\n" in value or "\r" in value:
            raise ValueError("headline must not contain newline characters")
        return value

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        if "\n\n" in value or "\r\n\r\n" in value:
            raise ValueError("summary must be a single paragraph")
        return value
