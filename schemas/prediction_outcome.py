from __future__ import annotations

from datetime import datetime

from pydantic import Field

from schemas._compat import CompatBaseModel
from schemas.shared_enums import FlowDirection, FlowMagnitude


class PredictionOutcome(CompatBaseModel):
    id: str | None = None
    navigation_signal_id: str
    route_prediction_id: str | None = None
    evaluation_window_hours: int
    prediction_accuracy: float = Field(ge=0.0, le=1.0)
    realized_direction: FlowDirection
    realized_magnitude: FlowMagnitude
    map_prediction_correct: bool
    notes: str
    created_by_agent: str
    created_at: datetime
