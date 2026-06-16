from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, StringConstraints
from typing_extensions import Annotated

from schemas._compat import CompatBaseModel
from schemas.shared_enums import RiskLevel

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
MarketBias = Literal["risk_on", "risk_off", "neutral", "transitioning"]
RouteClass = Literal["bridge", "cex", "chain", "defi", "staking", "perps", "other"]


class RouteSummary(CompatBaseModel):
    origin: NonEmptyString
    destination: NonEmptyString
    normalized_origin: NonEmptyString
    normalized_destination: NonEmptyString
    signal_type: NonEmptyString
    confidence: float = Field(ge=0.0, le=1.0)
    risk_level: RiskLevel
    signal_strength: float = Field(ge=0.0, le=1.0)
    route_score: float = Field(ge=0.0)
    signal_age_hours: float = Field(ge=0.0)
    route_class: RouteClass
    summary: NonEmptyString
    time_horizon_hours: int = Field(ge=0)


class HazardSummary(CompatBaseModel):
    origin: NonEmptyString
    destination: NonEmptyString
    normalized_origin: NonEmptyString
    normalized_destination: NonEmptyString
    confidence: float = Field(ge=0.0, le=1.0)
    risk_level: RiskLevel
    signal_age_hours: float = Field(ge=0.0)
    summary: NonEmptyString


class CongestionSummary(CompatBaseModel):
    origin: NonEmptyString
    destination: NonEmptyString
    normalized_origin: NonEmptyString
    normalized_destination: NonEmptyString
    confidence: float = Field(ge=0.0, le=1.0)
    risk_level: RiskLevel
    signal_age_hours: float = Field(ge=0.0)
    summary: NonEmptyString


class DestinationSummary(CompatBaseModel):
    destination: NonEmptyString
    normalized_destination: NonEmptyString
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_signal_count: int = Field(ge=0)


class EthereumRouteSummary(CompatBaseModel):
    origin: NonEmptyString
    destination: NonEmptyString
    normalized_origin: NonEmptyString
    normalized_destination: NonEmptyString
    confidence: float = Field(ge=0.0, le=1.0)
    risk_level: RiskLevel
    route_class: RouteClass
    summary: NonEmptyString
    signal_age_hours: float = Field(ge=0.0)


class CrossChainActivityState(CompatBaseModel):
    id: NonEmptyString
    scope: NonEmptyString = "global"
    market_bias: MarketBias
    top_routes: list[RouteSummary] = Field(default_factory=list, max_length=6)
    active_hazards: list[HazardSummary] = Field(default_factory=list, max_length=6)
    active_congestion: list[CongestionSummary] = Field(default_factory=list, max_length=6)
    top_destinations: list[DestinationSummary] = Field(default_factory=list, max_length=6)
    ethereum_outbound_routes: list[EthereumRouteSummary] = Field(
        default_factory=list, max_length=6
    )
    ethereum_inbound_routes: list[EthereumRouteSummary] = Field(
        default_factory=list, max_length=6
    )
    supporting_signal_ids: list[NonEmptyString] = Field(default_factory=list, max_length=20)
    created_by_agent: NonEmptyString = "cross_chain_activity_assembler"
    schema_version: str = ""
    created_at: datetime
