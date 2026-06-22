from __future__ import annotations

import sys

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):
        """Minimal Python 3.10 backport of StrEnum."""

        def __new__(cls, value: str) -> "StrEnum":
            obj = str.__new__(cls, value)
            obj._value_ = value
            return obj

        def __str__(self) -> str:
            return str(self.value)


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
    # Reflexivity management — route is crowded because of Maps consumers, not despite them.
    MAP_INDUCED_CONGESTION = "map_induced_congestion"
    # Cross-chain bridge flow synthesis — early-warning capital migration across chains.
    CROSS_CHAIN_BRIDGE_FLOW = "cross_chain_bridge_flow"


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


class EdgeStatus(StrEnum):
    ACTIVE = "active"
    NEW = "new"
    STRENGTHENING = "strengthening"
    WEAKENING = "weakening"
    CLOSED = "closed"


class DraftStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"


class HypothesisStatus(StrEnum):
    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    VALIDATED = "validated"
    REJECTED = "rejected"


class DriftSeverity(StrEnum):
    NONE = "none"
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


class AnomalySeverity(StrEnum):
    ELEVATED = "elevated"
    HIGH = "high"
    CRITICAL = "critical"


def is_known_signal_type(value: str) -> bool:
    return value in {member.value for member in SignalType}
