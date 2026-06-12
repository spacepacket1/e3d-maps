from __future__ import annotations

from schemas.navigation_signal import NavigationSignal
from schemas.recommendation import Recommendation
from schemas.route_prediction import RoutePrediction
from schemas.shared_enums import RiskLevel

_OPPORTUNITY_TYPES = frozenset({
    "capital_migration",
    "destination_prediction",
    "narrative_acceleration",
    "capital_conviction",
    "liquidity_forecast",
    "route_emergence",
    "agent_swarm_formation",
})
_HAZARD_TYPES = frozenset({"route_hazard", "route_closure"})
_CONGESTION_TYPES = frozenset({"congestion_formation"})

_RISK_INT: dict[str, int] = {
    RiskLevel.LOW: 15,
    RiskLevel.MEDIUM: 35,
    RiskLevel.HIGH: 60,
    RiskLevel.CRITICAL: 80,
}

# Maps story_type slugs to the signal types they cover, used for filtering.
STORY_TYPE_SIGNAL_TYPES: dict[str, frozenset[str]] = {
    "capital_migration": frozenset({"capital_migration", "destination_prediction"}),
    "exchange_flow": frozenset({"capital_migration", "route_hazard", "liquidity_forecast"}),
    "stablecoin_activity": frozenset({"capital_migration", "destination_prediction", "liquidity_forecast"}),
    "wallet_accumulation": frozenset({"capital_migration", "destination_prediction", "capital_conviction"}),
    "whale_movement": frozenset({"capital_migration", "route_hazard", "destination_prediction"}),
}

_SIGNAL_TYPE_TO_STORY_TYPE: dict[str, str] = {
    "capital_migration": "CapitalRotation",
    "destination_prediction": "CapitalRotation",
    "route_hazard": "RouteHazard",
    "route_closure": "RouteHazard",
    "congestion_formation": "Congestion",
    "narrative_acceleration": "NarrativeAcceleration",
    "capital_conviction": "WalletAccumulation",
    "liquidity_forecast": "LiquidityForecast",
}


def synthesize_recommendations(
    signals: list[NavigationSignal],
    routes: list[RoutePrediction],
    *,
    objective: str | None,
    max_results: int = 10,
) -> list[Recommendation]:
    if not signals and not routes:
        return []

    # Index routes by their originating signal ID.
    routes_by_signal: dict[str, list[str]] = {}
    for route in routes:
        if route.navigation_signal_id:
            routes_by_signal.setdefault(route.navigation_signal_id, []).append(route.id or "")

    # Group signals by (primary_asset, category).
    groups: dict[tuple[str, str], list[NavigationSignal]] = {}
    for signal in signals:
        primary_asset = signal.asset_scope[0] if signal.asset_scope else "global"
        if signal.signal_type in _HAZARD_TYPES:
            category = "hazard"
        elif signal.signal_type in _CONGESTION_TYPES:
            category = "congestion"
        else:
            category = "opportunity"
        groups.setdefault((primary_asset, category), []).append(signal)

    recommendations: list[Recommendation] = []
    for (primary_asset, category), group_signals in groups.items():
        sorted_sigs = sorted(group_signals, key=lambda s: s.confidence, reverse=True)
        primary_sigs = sorted_sigs[:3]
        signal_types = {s.signal_type for s in group_signals}

        supporting_signal_ids = [s.id for s in group_signals if s.id]
        supporting_route_ids: list[str] = []
        for sig in group_signals:
            if sig.id:
                supporting_route_ids.extend(r for r in routes_by_signal.get(sig.id, []) if r)

        title = _derive_title(primary_asset, category, primary_sigs)
        action = _derive_action(signal_types, objective, category)
        confidence = int(round(sorted_sigs[0].confidence * 100))
        risk = max((_RISK_INT.get(s.risk_level, 35) for s in group_signals), default=35)
        score = _compute_score(confidence, risk, len(supporting_signal_ids))
        reasoning = [s.answer for s in primary_sigs if s.answer]
        if len(group_signals) > 1:
            reasoning.append(f"{len(group_signals)} supporting signals")
        story_type = _SIGNAL_TYPE_TO_STORY_TYPE.get(primary_sigs[0].signal_type if primary_sigs else "")

        recommendations.append(Recommendation(
            rank=0,
            title=title,
            action=action,
            confidence=confidence,
            risk=risk,
            score=score,
            reasoning=reasoning[:5],
            supporting_signals=supporting_signal_ids,
            supporting_routes=supporting_route_ids,
            story_type=story_type,
        ))

    recommendations.sort(key=lambda r: (r.score, r.confidence), reverse=True)

    result: list[Recommendation] = []
    for rank, rec in enumerate(recommendations[:max_results], 1):
        result.append(rec.model_copy(update={"rank": rank}))
    return result


def _derive_title(asset: str, category: str, signals: list[NavigationSignal]) -> str:
    label = asset.upper() if asset != "global" else "Market"
    if category == "hazard":
        return f"Hazard Alert: {label}"
    if category == "congestion":
        return f"{label} Congestion Detected"
    if signals:
        stype = signals[0].signal_type
        dest = signals[0].destination or label
        if stype == "capital_migration":
            return f"Capital Rotating to {dest}"
        if stype == "destination_prediction":
            return f"Destination Emerging: {dest}"
        if stype == "narrative_acceleration":
            return f"Narrative Accelerating: {label}"
        if stype == "capital_conviction":
            return f"Strong Conviction Signal: {label}"
        if stype == "liquidity_forecast":
            return f"Liquidity Forecast: {label}"
    return f"Monitor {label}"


def _derive_action(signal_types: set[str], objective: str | None, category: str) -> str:
    if category == "hazard":
        return "avoid"
    if category == "congestion":
        return "wait"
    if objective == "grow_capital":
        return "increase_exposure"
    if objective == "preserve_capital":
        return "hold"
    if objective == "reduce_risk":
        return "reduce_exposure"
    if objective == "seek_opportunity":
        return "increase_attention"
    if objective == "monitor_market":
        return "monitor"
    if "capital_migration" in signal_types or "destination_prediction" in signal_types:
        return "investigate"
    return "monitor"


def _compute_score(confidence: int, risk: int, signal_count: int) -> int:
    supporting_bonus = min(10, signal_count * 3)
    raw = confidence - risk // 4 + supporting_bonus
    return max(0, min(100, raw))
