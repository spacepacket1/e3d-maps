from __future__ import annotations

from datetime import datetime

from pydantic import Field

from schemas._compat import CompatBaseModel
from schemas.shared_enums import AnomalySeverity


class SignalRateAnomaly(CompatBaseModel):
    """Detected spike in NavigationSignal generation rate for a signal type.

    Written by jobs/monitor_anomalies.py. The Watch Agent reads this table to
    prioritise its candidate queue. Purely deterministic — no LLM.
    """

    id: str | None = None
    signal_type: str
    baseline_rate_per_hour: float = Field(ge=0.0)
    observed_rate_per_hour: float = Field(ge=0.0)
    spike_ratio: float = Field(ge=0.0)
    severity: AnomalySeverity
    detected_at: datetime
