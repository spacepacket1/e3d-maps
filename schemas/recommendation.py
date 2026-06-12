from __future__ import annotations

from pydantic import Field

from schemas._compat import CompatBaseModel


class Recommendation(CompatBaseModel):
    rank: int
    title: str
    action: str
    confidence: int = Field(ge=0, le=100)
    risk: int = Field(ge=0, le=100)
    score: int = Field(ge=0, le=100)
    reasoning: list[str] = Field(default_factory=list)
    supporting_signals: list[str] = Field(default_factory=list)
    supporting_routes: list[str] = Field(default_factory=list)
    story_type: str | None = None
