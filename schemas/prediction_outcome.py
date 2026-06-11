from __future__ import annotations

from datetime import datetime

from pydantic import Field

from schemas._compat import CompatBaseModel
from schemas.shared_enums import FlowDirection, FlowMagnitude, ScoringMethod


class PredictionOutcome(CompatBaseModel):
    id: str | None = None
    navigation_signal_id: str
    route_prediction_id: str | None = None
    evaluation_window_hours: int

    # Primary blended accuracy (backward-compatible field).
    prediction_accuracy: float = Field(ge=0.0, le=1.0)
    realized_direction: FlowDirection
    realized_magnitude: FlowMagnitude
    map_prediction_correct: bool
    notes: str
    created_by_agent: str
    created_at: datetime

    # --- Phase 12 dual-scorer fields (MAPS-1201/1202) ---

    # Per-scorer accuracy values. None when that scorer did not run.
    heuristic_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    quantitative_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)

    # Absolute difference between the two scorers; None when only one ran.
    scorer_agreement: float | None = Field(default=None, ge=0.0, le=1.0)

    # Which scoring path produced prediction_accuracy.
    scoring_method: ScoringMethod = ScoringMethod.HEURISTIC

    # How many downstream agents/actions acted on this signal before the
    # evaluation window closed. Defaults to 0 (never null) so reflexivity
    # metrics are always queryable.
    consumer_exposure: int = Field(default=0, ge=0)

    # Accuracy split by exposure: exogenous = no downstream action used this
    # signal (consumer_exposure == 0); induced = at least one did.
    # Populated by compute_signal_utility_scores once exposure data is available.
    exogenous_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    induced_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
