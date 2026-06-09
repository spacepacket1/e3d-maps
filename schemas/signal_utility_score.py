from __future__ import annotations

from datetime import datetime

from pydantic import Field

from schemas._compat import CompatBaseModel


class SignalUtilityScore(CompatBaseModel):
    id: str | None = None
    navigation_signal_id: str
    sample_size: int
    prediction_accuracy: float = Field(ge=0.0, le=1.0)
    economic_utility: float = Field(ge=0.0, le=1.0)
    risk_reduction_utility: float = Field(ge=0.0, le=1.0)
    confidence_calibration_error: float = Field(ge=0.0, le=1.0)
    execution_adjusted_utility: float = Field(ge=0.0, le=1.0)
    final_signal_utility_score: float = Field(ge=0.0, le=1.0)
    linked_action_ids: list[str] = Field(default_factory=list)
    linked_outcome_ids: list[str] = Field(default_factory=list)
    created_at: datetime
