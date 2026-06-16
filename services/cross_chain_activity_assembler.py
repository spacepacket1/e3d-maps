from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from hashlib import sha1
import re

from schemas.cross_chain_activity_state import (
    CongestionSummary,
    CrossChainActivityState,
    DestinationSummary,
    EthereumRouteSummary,
    HazardSummary,
    RouteSummary,
)
from schemas.navigation_signal import NavigationSignal
from schemas.shared_enums import RiskLevel
from schemas.traffic_state import TrafficState

_ALLOWED_SIGNAL_TYPES = frozenset(
    {
        "capital_migration",
        "destination_prediction",
        "route_emergence",
        "route_hazard",
        "route_closure",
        "congestion_formation",
    }
)

_OPPORTUNITY_SIGNAL_TYPES = frozenset(
    {
        "capital_migration",
        "destination_prediction",
        "route_emergence",
    }
)

_HAZARD_SIGNAL_TYPES = frozenset({"route_hazard", "route_closure"})
_CONGESTION_SIGNAL_TYPES = frozenset({"congestion_formation"})

_TRACKED_CHAINS = frozenset({"ethereum", "solana", "base", "arbitrum", "optimism"})
_CANONICAL_VOCABULARY = frozenset(
    {
        "ethereum",
        "ethereum_bridges",
        "solana",
        "base",
        "arbitrum",
        "optimism",
        "binance",
        "cex",
        "cross_chain_bridges",
        "eth_defi",
        "solana_defi",
        "base_defi",
        "arbitrum_defi",
        "optimism_defi",
        "stablecoins",
        "perps",
    }
)
_TEXT_ROUTE_CONCEPTS = ("bridge", "bridges", "binance", "cex", "exchange", "l2", "layer 2")

_SIGNAL_TYPE_WEIGHTS = {
    "route_closure": 1.20,
    "route_hazard": 1.10,
    "route_emergence": 1.00,
    "capital_migration": 0.95,
    "destination_prediction": 0.90,
    "congestion_formation": 0.90,
}

_RISK_MULTIPLIERS = {
    RiskLevel.LOW: 0.85,
    RiskLevel.MEDIUM: 1.00,
    RiskLevel.HIGH: 1.12,
    RiskLevel.CRITICAL: 1.25,
}

_RISK_RANK = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}

_ETHEREUM_NODES = frozenset({"ethereum", "eth_defi", "ethereum_bridges"})
_CEX_NODES = frozenset({"binance", "cex"})
_BRIDGE_NODES = frozenset({"cross_chain_bridges", "ethereum_bridges"})


def assemble_cross_chain_activity_state(
    signals: list[NavigationSignal],
    traffic_state: TrafficState | None = None,
) -> CrossChainActivityState:
    """Build a deterministic cross-chain activity state from in-memory inputs."""
    created_at = _derive_created_at(signals, traffic_state)
    relevant_signals = [_ for _ in signals if _is_relevant_signal(_)]
    market_bias = traffic_state.market_state.value if traffic_state else "neutral"

    if not relevant_signals:
        return CrossChainActivityState(
            id=_build_state_id([], market_bias, created_at),
            market_bias=market_bias,
            supporting_signal_ids=[],
            schema_version="1.0",
            created_at=created_at,
        )

    route_candidates = [_build_route_candidate(signal, created_at) for signal in relevant_signals]
    route_candidates = [candidate for candidate in route_candidates if candidate is not None]

    if not route_candidates:
        return CrossChainActivityState(
            id=_build_state_id([], market_bias, created_at),
            market_bias=market_bias,
            supporting_signal_ids=[],
            schema_version="1.0",
            created_at=created_at,
        )

    opportunity_candidates = [
        candidate for candidate in route_candidates if candidate.signal.signal_type in _OPPORTUNITY_SIGNAL_TYPES
    ]
    opportunity_candidates.sort(key=_route_sort_key)
    top_routes = [_to_route_summary(candidate) for candidate in opportunity_candidates[:6]]

    hazard_candidates = [
        candidate
        for candidate in route_candidates
        if candidate.signal.signal_type in _HAZARD_SIGNAL_TYPES
    ]
    hazard_candidates.sort(key=_hazard_sort_key)
    active_hazards = [_to_hazard_summary(candidate) for candidate in hazard_candidates[:6]]

    congestion_candidates = [
        candidate
        for candidate in route_candidates
        if candidate.signal.signal_type in _CONGESTION_SIGNAL_TYPES
    ]
    congestion_candidates.sort(key=_route_sort_key)
    active_congestion = [_to_congestion_summary(candidate) for candidate in congestion_candidates[:6]]

    top_destinations = _build_top_destinations(opportunity_candidates)
    ethereum_outbound_routes = _build_ethereum_routes(route_candidates, direction="outbound")
    ethereum_inbound_routes = _build_ethereum_routes(route_candidates, direction="inbound")

    supporting_signal_ids = _supporting_signal_ids(route_candidates)
    return CrossChainActivityState(
        id=_build_state_id(supporting_signal_ids, market_bias, created_at),
        market_bias=market_bias,
        top_routes=top_routes,
        active_hazards=active_hazards,
        active_congestion=active_congestion,
        top_destinations=top_destinations,
        ethereum_outbound_routes=ethereum_outbound_routes,
        ethereum_inbound_routes=ethereum_inbound_routes,
        supporting_signal_ids=supporting_signal_ids,
        schema_version="1.0",
        created_at=created_at,
    )


class _RouteCandidate:
    def __init__(
        self,
        *,
        signal: NavigationSignal,
        normalized_origin: str,
        normalized_destination: str,
        route_class: str,
        signal_age_hours: float,
        route_score: float,
        hazard_score: float,
    ) -> None:
        self.signal = signal
        self.normalized_origin = normalized_origin
        self.normalized_destination = normalized_destination
        self.route_class = route_class
        self.signal_age_hours = signal_age_hours
        self.route_score = route_score
        self.hazard_score = hazard_score


def _build_route_candidate(
    signal: NavigationSignal, created_at: datetime
) -> _RouteCandidate | None:
    normalized_origin = _normalize_label(signal.origin, counterpart=signal.destination)
    normalized_destination = _normalize_label(signal.destination, counterpart=signal.origin)

    if not normalized_origin and not normalized_destination:
        return None

    age_hours = _signal_age_hours(signal, created_at)
    recency_multiplier = _recency_multiplier(age_hours)
    signal_type_weight = _SIGNAL_TYPE_WEIGHTS[signal.signal_type]
    route_score = signal.confidence * signal_type_weight * recency_multiplier
    hazard_score = (
        signal.confidence
        * signal_type_weight
        * _RISK_MULTIPLIERS[signal.risk_level]
        * recency_multiplier
    )

    candidate = _RouteCandidate(
        signal=signal,
        normalized_origin=normalized_origin or "unknown",
        normalized_destination=normalized_destination or "unknown",
        route_class=_classify_route(normalized_origin, normalized_destination),
        signal_age_hours=age_hours,
        route_score=route_score,
        hazard_score=hazard_score,
    )
    return candidate


def _derive_created_at(
    signals: list[NavigationSignal], traffic_state: TrafficState | None
) -> datetime:
    timestamps = [signal.created_at for signal in signals]
    if traffic_state is not None:
        timestamps.append(traffic_state.created_at)
    if not timestamps:
        return datetime(1970, 1, 1)
    return max(_naive_utc(ts) for ts in timestamps)


def _is_relevant_signal(signal: NavigationSignal) -> bool:
    if signal.signal_type not in _ALLOWED_SIGNAL_TYPES:
        return False
    if signal.confidence < 0.5:
        return False

    for label in (signal.origin, signal.destination):
        normalized = _normalize_label(label)
        if normalized in _CANONICAL_VOCABULARY:
            return True

    for chain_label in signal.chain_scope:
        normalized_chain = _normalize_label(chain_label)
        if normalized_chain in _TRACKED_CHAINS:
            return True

    for asset_label in signal.asset_scope:
        normalized_asset = _normalize_label(asset_label)
        if normalized_asset in _CANONICAL_VOCABULARY or normalized_asset in _TRACKED_CHAINS:
            return True

    answer_text = signal.answer.lower()
    return any(concept in answer_text for concept in _TEXT_ROUTE_CONCEPTS)


def _normalize_label(label: str | None, *, counterpart: str | None = None) -> str | None:
    if not label:
        return None

    value = _slug(label)
    counterpart_value = _slug(counterpart or "")

    if value in {"binance", "binance_exchange"}:
        return "binance"
    if value in {"cex", "exchange", "exchanges", "centralized_exchange", "centralized_exchanges"}:
        return "cex"
    if value in {"ethereum", "eth", "ethereum_chain"}:
        return "ethereum"
    if value in {"eth_defi", "ethereum_defi"}:
        return "eth_defi"
    if value in {"solana", "sol", "solana_chain"}:
        return "solana"
    if value in {"solana_defi", "sol_defi"}:
        return "solana_defi"
    if value in {"base", "base_chain"}:
        return "base"
    if value == "base_defi":
        return "base_defi"
    if value in {"arbitrum", "arb", "arbitrum_one"}:
        return "arbitrum"
    if value in {"arbitrum_defi", "arb_defi"}:
        return "arbitrum_defi"
    if value in {"optimism", "op", "optimism_chain"}:
        return "optimism"
    if value in {"optimism_defi", "op_defi"}:
        return "optimism_defi"
    if value in {"stablecoin", "stablecoins"}:
        return "stablecoins"
    if value == "perps":
        return "perps"

    bridge_like = value in {
        "bridge",
        "bridges",
        "cross_chain_bridge",
        "cross_chain_bridges",
        "eth_bridge",
        "ethereum_bridge",
        "ethereum_bridges",
    }
    if bridge_like:
        if value in {"eth_bridge", "ethereum_bridge", "ethereum_bridges"}:
            return "ethereum_bridges"
        if counterpart_value in {"ethereum", "eth", "eth_defi", "ethereum_defi"}:
            return "ethereum_bridges"
        return "cross_chain_bridges"

    return value or None


def _slug(value: str) -> str:
    normalized = value.strip().lower()
    normalized = normalized.replace("&", "and")
    normalized = re.sub(r"[\s/-]+", "_", normalized)
    normalized = re.sub(r"[^a-z0-9_]", "", normalized)
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.strip("_")


def _classify_route(origin: str | None, destination: str | None) -> str:
    if origin in _CEX_NODES or destination in _CEX_NODES:
        return "cex"
    if origin in _BRIDGE_NODES or destination in _BRIDGE_NODES:
        return "bridge"
    if origin in _TRACKED_CHAINS or destination in _TRACKED_CHAINS:
        return "chain"
    if (origin and origin.endswith("_defi")) or (destination and destination.endswith("_defi")):
        return "defi"
    if origin == "perps" or destination == "perps":
        return "perps"
    return "other"


def _signal_age_hours(signal: NavigationSignal, created_at: datetime) -> float:
    delta = created_at - _naive_utc(signal.created_at)
    return max(delta.total_seconds() / 3600.0, 0.0)


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _recency_multiplier(age_hours: float) -> float:
    if age_hours <= 2:
        return 1.00
    if age_hours <= 6:
        return 0.92
    if age_hours <= 12:
        return 0.84
    return 0.76


def _route_sort_key(candidate: _RouteCandidate) -> tuple[float, int, datetime, str]:
    return (
        -candidate.route_score,
        -_RISK_RANK[candidate.signal.risk_level],
        -_naive_utc(candidate.signal.created_at).timestamp(),
        candidate.signal.id or "",
    )


def _hazard_sort_key(candidate: _RouteCandidate) -> tuple[float, float, datetime, str]:
    return (
        -candidate.hazard_score,
        -candidate.route_score,
        -_naive_utc(candidate.signal.created_at).timestamp(),
        candidate.signal.id or "",
    )


def _build_top_destinations(candidates: list[_RouteCandidate]) -> list[DestinationSummary]:
    groups: dict[str, list[_RouteCandidate]] = defaultdict(list)
    for candidate in candidates:
        if candidate.normalized_destination != "unknown":
            groups[candidate.normalized_destination].append(candidate)

    ranked: list[DestinationSummary] = []
    for normalized_destination, group in groups.items():
        ranked.append(
            DestinationSummary(
                destination=group[0].signal.destination or normalized_destination,
                normalized_destination=normalized_destination,
                confidence=max(item.signal.confidence for item in group),
                supporting_signal_count=len(group),
            )
        )

    ranked.sort(
        key=lambda item: (
            -item.supporting_signal_count,
            -item.confidence,
            item.normalized_destination,
        )
    )
    return ranked[:6]


def _build_ethereum_routes(
    candidates: list[_RouteCandidate], *, direction: str
) -> list[EthereumRouteSummary]:
    selected: list[_RouteCandidate] = []
    for candidate in candidates:
        origin = candidate.normalized_origin
        destination = candidate.normalized_destination

        if direction == "outbound":
            if origin in {"ethereum", "eth_defi"} and destination not in {"ethereum", "eth_defi"}:
                selected.append(candidate)
            elif origin == "ethereum_bridges" and destination not in _ETHEREUM_NODES:
                selected.append(candidate)
        elif direction == "inbound":
            if destination in {"ethereum", "eth_defi"} and origin not in {"ethereum", "eth_defi"}:
                selected.append(candidate)
        else:
            raise ValueError(f"Unknown direction: {direction}")

    selected.sort(key=_route_sort_key)
    return [_to_ethereum_route_summary(candidate) for candidate in selected[:6]]


def _supporting_signal_ids(candidates: list[_RouteCandidate]) -> list[str]:
    seen: set[str] = set()
    ids: list[str] = []
    for candidate in sorted(candidates, key=_route_sort_key):
        signal_id = candidate.signal.id
        if not signal_id or signal_id in seen:
            continue
        seen.add(signal_id)
        ids.append(signal_id)
        if len(ids) >= 20:
            break
    return ids


def _to_route_summary(candidate: _RouteCandidate) -> RouteSummary:
    signal = candidate.signal
    return RouteSummary(
        origin=signal.origin or candidate.normalized_origin,
        destination=signal.destination or candidate.normalized_destination,
        normalized_origin=candidate.normalized_origin,
        normalized_destination=candidate.normalized_destination,
        signal_type=signal.signal_type,
        confidence=signal.confidence,
        risk_level=signal.risk_level,
        signal_strength=signal.confidence,
        route_score=round(candidate.route_score, 6),
        signal_age_hours=round(candidate.signal_age_hours, 3),
        route_class=candidate.route_class,
        summary=(signal.answer or "").strip() or "Cross-chain route signal detected.",
        time_horizon_hours=signal.time_horizon_hours,
    )


def _to_hazard_summary(candidate: _RouteCandidate) -> HazardSummary:
    signal = candidate.signal
    return HazardSummary(
        origin=signal.origin or candidate.normalized_origin,
        destination=signal.destination or candidate.normalized_destination,
        normalized_origin=candidate.normalized_origin,
        normalized_destination=candidate.normalized_destination,
        confidence=signal.confidence,
        risk_level=signal.risk_level,
        signal_age_hours=round(candidate.signal_age_hours, 3),
        summary=(signal.answer or "").strip() or "Route hazard detected.",
    )


def _to_congestion_summary(candidate: _RouteCandidate) -> CongestionSummary:
    signal = candidate.signal
    return CongestionSummary(
        origin=signal.origin or candidate.normalized_origin,
        destination=signal.destination or candidate.normalized_destination,
        normalized_origin=candidate.normalized_origin,
        normalized_destination=candidate.normalized_destination,
        confidence=signal.confidence,
        risk_level=signal.risk_level,
        signal_age_hours=round(candidate.signal_age_hours, 3),
        summary=(signal.answer or "").strip() or "Cross-chain congestion detected.",
    )


def _to_ethereum_route_summary(candidate: _RouteCandidate) -> EthereumRouteSummary:
    signal = candidate.signal
    return EthereumRouteSummary(
        origin=signal.origin or candidate.normalized_origin,
        destination=signal.destination or candidate.normalized_destination,
        normalized_origin=candidate.normalized_origin,
        normalized_destination=candidate.normalized_destination,
        confidence=signal.confidence,
        risk_level=signal.risk_level,
        route_class=candidate.route_class,
        summary=(signal.answer or "").strip() or "Ethereum-linked route detected.",
        signal_age_hours=round(candidate.signal_age_hours, 3),
    )


def _build_state_id(signal_ids: list[str], market_bias: str, created_at: datetime) -> str:
    fingerprint = "|".join([market_bias, created_at.isoformat(), *signal_ids])
    digest = sha1(fingerprint.encode("utf-8")).hexdigest()[:12]
    return f"ccas_{digest}"
