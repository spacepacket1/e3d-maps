from __future__ import annotations

from datetime import datetime

from pydantic import Field

from schemas._compat import CompatBaseModel


class QueryAccessLog(CompatBaseModel):
    """One anonymised record of a Maps API query that carried intent signals."""

    id: str | None = None
    endpoint: str
    destination_filter: str | None = None
    signal_type_filter: str | None = None
    time_horizon_hours_filter: int | None = None
    # SHA-256 of api_key or remote IP, truncated to 16 hex chars for k-anonymity.
    caller_id_hash: str
    requested_at: datetime


class DestinationQueryCount(CompatBaseModel):
    destination: str
    count: int


class SignalTypeQueryCount(CompatBaseModel):
    signal_type: str
    count: int


class SignalDemandState(CompatBaseModel):
    """Aggregated query-demand snapshot over a time window."""

    id: str | None = None
    window_start: datetime
    window_end: datetime
    total_queries: int = Field(ge=0)
    queries_by_destination: list[DestinationQueryCount] = Field(default_factory=list)
    queries_by_signal_type: list[SignalTypeQueryCount] = Field(default_factory=list)
    avg_requested_time_horizon_hours: float | None = None
    # "shrinking" means agents are asking for shorter horizons — urgency rising.
    urgency_trend: str = "stable"
    top_destinations: list[str] = Field(default_factory=list)
    # Destinations whose query rate is ≥2× the 24-hour rolling baseline.
    demand_surge_destinations: list[str] = Field(default_factory=list)
    created_at: datetime
