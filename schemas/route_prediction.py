from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from schemas._compat import CompatBaseModel
from schemas.shared_enums import FlowDirection, FlowMagnitude, is_known_signal_type


class RoutePrediction(CompatBaseModel):
    id: str | None = None
    navigation_signal_id: str
    route_type: str
    origin: str
    destination: str
    expected_flow_direction: FlowDirection
    expected_flow_magnitude: FlowMagnitude
    time_horizon_hours: int
    confidence: float = Field(ge=0.0, le=1.0)
    hazards: list[str] = Field(default_factory=list)
    supporting_story_ids: list[str] = Field(default_factory=list)
    created_by_agent: str | None = None
    model: str | None = None
    adapter: str | None = None
    schema_version: str | None = None
    created_at: datetime

    @field_validator("route_type")
    @classmethod
    def validate_route_type(cls, value: str) -> str:
        if not is_known_signal_type(value):
            raise ValueError(f"Unknown signal type: {value}")
        return value

    @classmethod
    def model_validate(cls, obj, context=None):
        allow_unknown = bool((context or {}).get("allow_unknown_signal_types"))
        if allow_unknown and isinstance(obj, dict):
            raw_route_type = obj.get("route_type")
            if raw_route_type is not None and not is_known_signal_type(raw_route_type):
                patched = dict(obj)
                patched["route_type"] = "destination_prediction"
                model = super().model_validate(patched, context=context)
                model.route_type = raw_route_type
                return model
        return super().model_validate(obj, context=context)
