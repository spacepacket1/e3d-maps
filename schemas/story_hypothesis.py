from __future__ import annotations

from datetime import datetime

from pydantic import Field

from schemas._compat import CompatBaseModel
from schemas.shared_enums import HypothesisStatus


class HypothesisEvidence(CompatBaseModel):
    type: str
    id: str
    summary: str


class StoryHypothesis(CompatBaseModel):
    """A candidate new story type proposed by the StoryHypothesisAgent.

    Status starts as "proposed". A human must advance it to "validated" before
    the spacepacket story pipeline is updated. Rejected hypotheses stay in the
    table for audit purposes.
    """

    id: str | None = None
    proposed_story_type: str
    description: str
    detection_rationale: str
    # Narrative descriptions of on-chain patterns that motivated the hypothesis.
    supporting_on_chain_patterns: list[str] = Field(default_factory=list)
    # Existing story types this new type resembles or diverges from.
    related_existing_story_types: list[str] = Field(default_factory=list)
    example_evidence: list[HypothesisEvidence] = Field(default_factory=list)
    supporting_signal_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    created_by_agent: str
    created_at: datetime
