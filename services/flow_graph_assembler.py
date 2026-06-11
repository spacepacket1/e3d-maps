from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from uuid import uuid4

from schemas.flow_graph import FlowEdge, FlowGraphSnapshot
from schemas.navigation_signal import NavigationSignal
from schemas.shared_enums import EdgeStatus, RiskLevel, SignalStrength

# Signal types that elevate hazard level on an edge.
_HAZARD_LEVELS: dict[str, RiskLevel] = {
    "route_hazard": RiskLevel.HIGH,
    "route_closure": RiskLevel.HIGH,
    "congestion_formation": RiskLevel.MEDIUM,
    "liquidity_forecast": RiskLevel.MEDIUM,
}

_HAZARD_RANK: dict[RiskLevel, int] = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}

# Confidence delta required to call an edge strengthening or weakening.
_DELTA_THRESHOLD = 0.10


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _confidence_to_strength(confidence: float) -> SignalStrength:
    if confidence >= 0.75:
        return SignalStrength.STRONG
    if confidence >= 0.50:
        return SignalStrength.MODERATE
    return SignalStrength.WEAK


def _max_hazard(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    return a if _HAZARD_RANK[a] >= _HAZARD_RANK[b] else b


def assemble(
    signals: list[NavigationSignal],
    *,
    prev_edges: list[FlowEdge] | None = None,
    now: datetime | None = None,
) -> tuple[FlowGraphSnapshot, list[FlowEdge]]:
    """Build a FlowGraph snapshot from a list of NavigationSignals.

    Compares against prev_edges (the latest existing snapshot) to compute
    edge deltas: new, strengthening, weakening, and closed edges.
    Returns a (snapshot, edges) tuple — IDs are assigned here.
    """
    ts = now or datetime.now(UTC).replace(tzinfo=None)
    snapshot_id = _gen_id("fg")

    prev_by_pair: dict[tuple[str, str], FlowEdge] = {
        (e.origin, e.destination): e for e in (prev_edges or [])
        if e.edge_status != EdgeStatus.CLOSED
    }

    # Group signals by (origin, destination). Skip signals without both.
    groups: dict[tuple[str, str], list[NavigationSignal]] = defaultdict(list)
    for sig in signals:
        if sig.origin and sig.destination:
            groups[(sig.origin, sig.destination)].append(sig)

    edges: list[FlowEdge] = []

    for (origin, destination), group in groups.items():
        confidence = max(s.confidence for s in group)
        hazard = RiskLevel.LOW
        for s in group:
            hazard = _max_hazard(hazard, _HAZARD_LEVELS.get(s.signal_type, RiskLevel.LOW))

        prev = prev_by_pair.get((origin, destination))
        if prev is None:
            status = EdgeStatus.NEW
        elif confidence - prev.confidence > _DELTA_THRESHOLD:
            status = EdgeStatus.STRENGTHENING
        elif prev.confidence - confidence > _DELTA_THRESHOLD:
            status = EdgeStatus.WEAKENING
        else:
            status = EdgeStatus.ACTIVE

        edges.append(FlowEdge(
            id=_gen_id("fge"),
            snapshot_id=snapshot_id,
            origin=origin,
            destination=destination,
            strength=_confidence_to_strength(confidence),
            confidence=confidence,
            hazard_level=hazard,
            source_signal_ids=[s.id for s in group if s.id],
            edge_status=status,
            created_at=ts,
        ))

    # Explicitly record edges that appeared in the previous snapshot but are
    # absent from the current one — agents can query "what routes just closed."
    current_pairs = set(groups.keys())
    for (origin, destination), prev_edge in prev_by_pair.items():
        if (origin, destination) not in current_pairs:
            edges.append(FlowEdge(
                id=_gen_id("fge"),
                snapshot_id=snapshot_id,
                origin=origin,
                destination=destination,
                strength=prev_edge.strength,
                confidence=0.0,
                hazard_level=prev_edge.hazard_level,
                source_signal_ids=[],
                edge_status=EdgeStatus.CLOSED,
                created_at=ts,
            ))

    active_edges = [e for e in edges if e.edge_status != EdgeStatus.CLOSED]
    nodes = {n for e in active_edges for n in (e.origin, e.destination)}

    snapshot = FlowGraphSnapshot(
        id=snapshot_id,
        signal_count=len(signals),
        node_count=len(nodes),
        edge_count=len(active_edges),
        created_at=ts,
    )

    return snapshot, edges
