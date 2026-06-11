from __future__ import annotations

from datetime import datetime

from pydantic import Field

from schemas._compat import CompatBaseModel
from schemas.shared_enums import EdgeStatus, RiskLevel, SignalStrength


class FlowEdge(CompatBaseModel):
    id: str | None = None
    snapshot_id: str
    origin: str
    destination: str
    strength: SignalStrength
    confidence: float = Field(ge=0.0, le=1.0)
    hazard_level: RiskLevel = RiskLevel.LOW
    source_signal_ids: list[str] = Field(default_factory=list)
    edge_status: EdgeStatus = EdgeStatus.ACTIVE
    created_at: datetime


class FlowGraphSnapshot(CompatBaseModel):
    id: str | None = None
    signal_count: int = Field(ge=0)
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    created_at: datetime
