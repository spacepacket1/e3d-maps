from __future__ import annotations

from datetime import datetime

from pydantic import Field, StringConstraints, field_validator
from typing_extensions import Annotated

from schemas._compat import CompatBaseModel
from schemas.shared_enums import DraftStatus

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class WatchDraft(CompatBaseModel):
    """A human-facing draft built from a WatchPrediction. v1 is draft-only and
    never auto-published."""

    id: str | None = None
    watch_prediction_id: str
    headline: NonEmptyString
    analysis: str
    significance: str
    x_post: str = Field(max_length=280)
    linkedin_draft: str
    track_record_snapshot: dict = Field(default_factory=dict)
    routing: dict = Field(default_factory=dict)
    status: DraftStatus = DraftStatus.DRAFT
    created_by_agent: str = "watch_draft_generator"
    model: str
    adapter: str
    schema_version: str
    created_at: datetime

    @field_validator("linkedin_draft")
    @classmethod
    def validate_linkedin_word_count(cls, value: str) -> str:
        if len(value.split()) < 150:
            raise ValueError("linkedin_draft must be at least 150 words")
        return value
