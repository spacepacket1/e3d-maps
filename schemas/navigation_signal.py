from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from schemas._compat import CompatBaseModel
from schemas.shared_enums import MarketState, OutcomeStatus, RiskLevel, SignalStrength, is_known_signal_type


class EvidenceItem(CompatBaseModel):
    type: str
    id: str
    summary: str


class RecommendedRoute(CompatBaseModel):
    origin: str
    destination: str
    route_type: str


class NavigationSignal(CompatBaseModel):
    id: str | None = None
    signal_type: str
    question: str
    answer: str
    origin: str | None = None
    destination: str | None = None
    asset_scope: list[str] = Field(default_factory=list)
    chain_scope: list[str] = Field(default_factory=list)
    time_horizon_hours: int
    confidence: float = Field(ge=0.0, le=1.0)
    risk_level: RiskLevel
    signal_strength: SignalStrength | None = None
    market_state: MarketState | None = None
    supporting_story_ids: list[str]
    supporting_thesis_ids: list[str] = Field(default_factory=list)
    supporting_action_ids: list[str] = Field(default_factory=list)
    supporting_outcome_ids: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    recommended_route: RecommendedRoute | None = None
    recommended_action: str | None = None
    created_by_agent: str
    model: str
    adapter: str
    schema_version: str
    outcome_status: OutcomeStatus
    created_at: datetime

    @field_validator("signal_type")
    @classmethod
    def validate_signal_type(cls, value: str) -> str:
        if not is_known_signal_type(value):
            raise ValueError(f"Unknown signal type: {value}")
        return value

    @classmethod
    def model_validate(cls, obj, context=None):
        allow_unknown = bool((context or {}).get("allow_unknown_signal_types"))
        if allow_unknown and isinstance(obj, dict):
            raw_signal_type = obj.get("signal_type")
            if raw_signal_type is not None and not is_known_signal_type(raw_signal_type):
                patched = dict(obj)
                patched["signal_type"] = "capital_migration"
                model = super().model_validate(patched, context=context)
                model.signal_type = raw_signal_type
                return model
        return super().model_validate(obj, context=context)
