from __future__ import annotations

from datetime import datetime

from schemas._compat import CompatBaseModel
from schemas.shared_enums import FlowDirection, FlowMagnitude


class ConsumerAttestation(CompatBaseModel):
    """A downstream agent's report that it acted (or not) on a watch prediction.

    Aggregated into ``PredictionOutcome.consumer_exposure`` to power the
    exogenous/induced reflexivity split (Phase 5)."""

    id: str | None = None
    watch_prediction_id: str
    consumer_id: str
    acted: bool
    observed_direction: FlowDirection | None = None
    observed_magnitude: FlowMagnitude | None = None
    notes: str = ""
    created_at: datetime
