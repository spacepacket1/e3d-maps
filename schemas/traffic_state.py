from __future__ import annotations

from datetime import datetime

from pydantic import Field

from schemas._compat import CompatBaseModel
from schemas.shared_enums import MarketState, SignalStrength


class DominantFlow(CompatBaseModel):
    origin: str
    destination: str
    strength: SignalStrength


class TopDestination(CompatBaseModel):
    destination: str
    confidence: float = Field(ge=0.0, le=1.0)


class TrafficState(CompatBaseModel):
    id: str | None = None
    scope: str
    market_state: MarketState
    dominant_flows: list[DominantFlow] = Field(default_factory=list)
    congestion_zones: list[str] = Field(default_factory=list)
    hazards: list[str] = Field(default_factory=list)
    top_destinations: list[TopDestination] = Field(default_factory=list)
    created_by_agent: str
    created_at: datetime
