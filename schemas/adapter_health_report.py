from __future__ import annotations

from datetime import datetime

from pydantic import Field

from schemas._compat import CompatBaseModel
from schemas.shared_enums import DriftSeverity


class CalibrationBucket(CompatBaseModel):
    """One confidence bucket in the reliability curve."""

    bucket_label: str          # e.g. "0.5-0.6"
    predicted_confidence: float = Field(ge=0.0, le=1.0)
    realized_accuracy: float = Field(ge=0.0, le=1.0)
    sample_size: int = Field(ge=0)
    # Flagged when sample_size < MIN_BUCKET_SAMPLES — calibration not credible yet.
    thin_data: bool = False


class AdapterHealthReport(CompatBaseModel):
    """Daily calibration + drift report for the deployed Maps adapter.

    Purely deterministic — no LLM involved.
    retraining_recommended = True when overall_calibration_error exceeds the
    configured MAPS_ADAPTER_HEALTH_DRIFT_THRESHOLD.
    """

    id: str | None = None
    adapter_name: str
    evaluation_window_days: int = Field(ge=1)
    total_scored_signals: int = Field(ge=0)
    # Mean |predicted_confidence - realized_accuracy| across all scored signals.
    overall_calibration_error: float | None = Field(default=None, ge=0.0, le=1.0)
    # Per signal-type realized accuracy (signal_type -> accuracy).
    accuracy_by_signal_type: dict[str, float] = Field(default_factory=dict)
    confidence_buckets: list[CalibrationBucket] = Field(default_factory=list)
    drift_detected: bool = False
    drift_severity: DriftSeverity = DriftSeverity.NONE
    retraining_recommended: bool = False
    notes: str = ""
    created_at: datetime
