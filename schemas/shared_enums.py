from __future__ import annotations

from enum import StrEnum


class SignalType(StrEnum):
    CAPITAL_MIGRATION = "capital_migration"
    CONGESTION_FORMATION = "congestion_formation"
    ROUTE_EMERGENCE = "route_emergence"
    ROUTE_CLOSURE = "route_closure"
    ROUTE_HAZARD = "route_hazard"
    DESTINATION_PREDICTION = "destination_prediction"
    LIQUIDITY_FORECAST = "liquidity_forecast"
    NARRATIVE_ACCELERATION = "narrative_acceleration"
    AGENT_SWARM_FORMATION = "agent_swarm_formation"
    CAPITAL_CONVICTION = "capital_conviction"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SignalStrength(StrEnum):
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


class MarketState(StrEnum):
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"
    NEUTRAL = "neutral"
    TRANSITIONING = "transitioning"


class OutcomeStatus(StrEnum):
    PENDING = "pending"
    CORRECT = "correct"
    INCORRECT = "incorrect"
    MIXED = "mixed"
    DISPUTED = "disputed"


class ScoringMethod(StrEnum):
    HEURISTIC = "heuristic"
    QUANTITATIVE = "quantitative"
    BLENDED = "blended"


class FlowDirection(StrEnum):
    INFLOW = "inflow"
    OUTFLOW = "outflow"
    NEUTRAL = "neutral"
    MIXED = "mixed"


class FlowMagnitude(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


def is_known_signal_type(value: str) -> bool:
    return value in {member.value for member in SignalType}
