from __future__ import annotations

from datetime import datetime

from pydantic import Field, StringConstraints
from typing_extensions import Annotated

from schemas._compat import CompatBaseModel
from schemas.shared_enums import FlowDirection, FlowMagnitude, OutcomeStatus, SignalType

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class WatchPrediction(CompatBaseModel):
    """A falsifiable, probabilistic claim derived from a consumed notable signal.

    The LLM only supplies ``claim`` + expected direction/magnitude/window; the
    numeric ``probability`` is derived deterministically (Phase 3), never
    self-reported by the model.
    """

    id: str | None = None
    source_signal_id: str
    source_prediction_id: str | None = None
    signal_type: SignalType
    asset_scope: list[str] = Field(default_factory=list)
    chain_scope: list[str] = Field(default_factory=list)
    claim: NonEmptyString
    probability: float = Field(ge=0.0, le=1.0)
    realized_direction_expected: FlowDirection
    magnitude_expected: FlowMagnitude
    evaluation_window_hours: int = Field(gt=0)
    status: OutcomeStatus = OutcomeStatus.PENDING
    created_by_agent: str = "watch_agent"
    model: str
    adapter: str
    schema_version: str
    idempotency_key: str
    created_at: datetime
