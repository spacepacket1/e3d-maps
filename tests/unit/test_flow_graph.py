from __future__ import annotations

import json
from datetime import datetime

from api.maps_routes import get_maps_graph, get_maps_graph_around
from schemas.flow_graph import FlowEdge, FlowGraphSnapshot
from schemas.navigation_signal import NavigationSignal
from schemas.shared_enums import EdgeStatus, RiskLevel, SignalStrength
from services.flow_graph_assembler import assemble
from services.maps_api_service import MapsAPIService


# ── Assembler tests ───────────────────────────────────────────────────────────

def _make_signal(**overrides) -> NavigationSignal:
    defaults = dict(
        id="sig_abc123",
        signal_type="capital_migration",
        question="Where is capital moving?",
        answer="Into ETH DeFi.",
        origin="stablecoins",
        destination="ETH_DEFI",
        asset_scope=["ETH"],
        chain_scope=["ethereum"],
        time_horizon_hours=24,
        confidence=0.72,
        risk_level="low",
        signal_strength="strong",
        market_state="risk_on",
        supporting_story_ids=[],
        supporting_thesis_ids=[],
        supporting_action_ids=[],
        supporting_outcome_ids=[],
        evidence=[],
        recommended_route=None,
        recommended_action="monitor",
        created_by_agent="capital_migration_agent",
        model="mlx-community/Qwen2.5-7B-Instruct-4bit",
        adapter="",
        schema_version="1",
        outcome_status="pending",
        created_at=datetime(2026, 6, 11, 9, 0, 0),
    )
    defaults.update(overrides)
    return NavigationSignal.model_validate(defaults)


NOW = datetime(2026, 6, 11, 10, 0, 0)


def test_assemble_creates_edge_from_signal():
    signals = [_make_signal()]
    snapshot, edges = assemble(signals, now=NOW)

    assert snapshot.signal_count == 1
    assert snapshot.node_count == 2  # stablecoins + ETH_DEFI
    assert snapshot.edge_count == 1

    active = [e for e in edges if e.edge_status != EdgeStatus.CLOSED]
    assert len(active) == 1
    edge = active[0]
    assert edge.origin == "stablecoins"
    assert edge.destination == "ETH_DEFI"
    assert edge.confidence == 0.72
    assert edge.strength == SignalStrength.MODERATE
    assert edge.hazard_level == RiskLevel.LOW
    assert edge.edge_status == EdgeStatus.NEW  # no prev edges
    assert edge.source_signal_ids == ["sig_abc123"]


def test_assemble_skips_signals_without_origin_or_destination():
    signals = [_make_signal(origin="", destination="ETH_DEFI")]
    snapshot, edges = assemble(signals, now=NOW)
    assert snapshot.edge_count == 0
    assert edges == []


def test_assemble_aggregates_multiple_signals_on_same_pair():
    signals = [
        _make_signal(id="sig_a", confidence=0.6),
        _make_signal(id="sig_b", confidence=0.8),
    ]
    snapshot, edges = assemble(signals, now=NOW)

    active = [e for e in edges if e.edge_status != EdgeStatus.CLOSED]
    assert len(active) == 1
    assert active[0].confidence == 0.8  # max
    assert set(active[0].source_signal_ids) == {"sig_a", "sig_b"}


def test_assemble_elevates_hazard_from_hazard_signals():
    signals = [_make_signal(signal_type="route_hazard")]
    _, edges = assemble(signals, now=NOW)
    active = [e for e in edges if e.edge_status != EdgeStatus.CLOSED]
    assert active[0].hazard_level == RiskLevel.HIGH


def test_assemble_detects_new_edge():
    signals = [_make_signal()]
    _, edges = assemble(signals, prev_edges=[], now=NOW)
    assert edges[0].edge_status == EdgeStatus.NEW


def test_assemble_detects_strengthening():
    prev_edge = FlowEdge(
        id="fge_prev",
        snapshot_id="fg_prev",
        origin="stablecoins",
        destination="ETH_DEFI",
        strength=SignalStrength.MODERATE,
        confidence=0.55,
        hazard_level=RiskLevel.LOW,
        source_signal_ids=[],
        edge_status=EdgeStatus.ACTIVE,
        created_at=NOW,
    )
    signals = [_make_signal(confidence=0.80)]  # delta = 0.25 > 0.10
    _, edges = assemble(signals, prev_edges=[prev_edge], now=NOW)
    active = [e for e in edges if e.edge_status != EdgeStatus.CLOSED]
    assert active[0].edge_status == EdgeStatus.STRENGTHENING


def test_assemble_detects_weakening():
    prev_edge = FlowEdge(
        id="fge_prev",
        snapshot_id="fg_prev",
        origin="stablecoins",
        destination="ETH_DEFI",
        strength=SignalStrength.STRONG,
        confidence=0.85,
        hazard_level=RiskLevel.LOW,
        source_signal_ids=[],
        edge_status=EdgeStatus.ACTIVE,
        created_at=NOW,
    )
    signals = [_make_signal(confidence=0.60)]  # delta = -0.25 < -0.10
    _, edges = assemble(signals, prev_edges=[prev_edge], now=NOW)
    active = [e for e in edges if e.edge_status != EdgeStatus.CLOSED]
    assert active[0].edge_status == EdgeStatus.WEAKENING


def test_assemble_marks_missing_prev_edges_as_closed():
    prev_edge = FlowEdge(
        id="fge_prev",
        snapshot_id="fg_prev",
        origin="BTC",
        destination="BTC_DEFI",
        strength=SignalStrength.WEAK,
        confidence=0.45,
        hazard_level=RiskLevel.LOW,
        source_signal_ids=[],
        edge_status=EdgeStatus.ACTIVE,
        created_at=NOW,
    )
    signals = [_make_signal()]  # stablecoins→ETH_DEFI only
    _, edges = assemble(signals, prev_edges=[prev_edge], now=NOW)

    closed = [e for e in edges if e.edge_status == EdgeStatus.CLOSED]
    assert len(closed) == 1
    assert closed[0].origin == "BTC"
    assert closed[0].destination == "BTC_DEFI"
    assert closed[0].confidence == 0.0


def test_assemble_strength_thresholds():
    _, edges_strong = assemble([_make_signal(confidence=0.75)], now=NOW)
    _, edges_moderate = assemble([_make_signal(confidence=0.60)], now=NOW)
    _, edges_weak = assemble([_make_signal(confidence=0.40)], now=NOW)

    assert [e for e in edges_strong if e.edge_status != EdgeStatus.CLOSED][0].strength == SignalStrength.STRONG
    assert [e for e in edges_moderate if e.edge_status != EdgeStatus.CLOSED][0].strength == SignalStrength.MODERATE
    assert [e for e in edges_weak if e.edge_status != EdgeStatus.CLOSED][0].strength == SignalStrength.WEAK


# ── API route tests ───────────────────────────────────────────────────────────

def _serialize(*rows) -> bytes:
    return ("\n".join(json.dumps(r) for r in rows) + "\n").encode()


_SNAPSHOT_ROW = {
    "id": "fg_snapshot01",
    "signal_count": 5,
    "node_count": 2,
    "edge_count": 1,
    "created_at": "2026-06-11 10:00:00",
}
_EDGE_ROW = {
    "id": "fge_edge01",
    "snapshot_id": "fg_snapshot01",
    "origin": "stablecoins",
    "destination": "ETH_DEFI",
    "strength": "moderate",
    "confidence": 0.72,
    "hazard_level": "low",
    "source_signal_ids": ["sig_abc123"],
    "edge_status": "new",
    "created_at": "2026-06-11 10:00:00",
}


def test_get_latest_flow_graph_returns_graph():
    def executor(body: bytes) -> bytes:
        sql = body.decode()
        if "FlowGraphSnapshots" in sql and "FlowGraphEdges" not in sql:
            return _serialize(_SNAPSHOT_ROW)
        return _serialize(_EDGE_ROW)

    service = MapsAPIService(query_executor=executor)
    result = service.get_latest_flow_graph()

    assert result is not None
    assert result["snapshot_id"] == "fg_snapshot01"
    assert result["nodes"] == ["ETH_DEFI", "stablecoins"]
    assert len(result["edges"]) == 1
    assert result["edges"][0]["edge_status"] == "new"


def test_get_latest_flow_graph_returns_none_when_no_snapshot():
    service = MapsAPIService(query_executor=lambda body: b"")
    assert service.get_latest_flow_graph() is None


def test_get_flow_graph_around_returns_subgraph():
    def executor(body: bytes) -> bytes:
        sql = body.decode()
        if "FlowGraphSnapshots" in sql:
            return _serialize({"id": "fg_snapshot01", "created_at": "2026-06-11 10:00:00"})
        return _serialize(_EDGE_ROW)

    service = MapsAPIService(query_executor=executor)
    result = service.get_flow_graph_around("ETH_DEFI")

    assert result["node"] == "ETH_DEFI"
    assert len(result["inbound"]) == 1
    assert result["inbound"][0]["origin"] == "stablecoins"
    assert result["outbound"] == []


def test_get_flow_graph_around_returns_empty_for_unknown_node():
    service = MapsAPIService(query_executor=lambda body: b"")
    result = service.get_flow_graph_around("UNKNOWN")
    assert result["node"] == "UNKNOWN"
    assert result["edges"] == []
    assert result["snapshot_id"] is None


def test_get_maps_graph_route_returns_404_when_no_snapshot():
    service = MapsAPIService(query_executor=lambda body: b"")
    response = get_maps_graph(service)
    assert response.status_code == 404
    assert response.body["error"] == "no_flow_graph_snapshot"


def test_get_maps_graph_route_returns_graph():
    def executor(body: bytes) -> bytes:
        sql = body.decode()
        if "FlowGraphSnapshots" in sql and "FlowGraphEdges" not in sql:
            return _serialize(_SNAPSHOT_ROW)
        return _serialize(_EDGE_ROW)

    service = MapsAPIService(query_executor=executor)
    response = get_maps_graph(service)

    assert response.status_code == 200
    assert response.body["status"] == "ok"
    assert response.body["graph"]["snapshot_id"] == "fg_snapshot01"
    assert len(response.body["graph"]["edges"]) == 1


def test_get_maps_graph_around_route():
    def executor(body: bytes) -> bytes:
        sql = body.decode()
        if "FlowGraphSnapshots" in sql:
            return _serialize({"id": "fg_snapshot01", "created_at": "2026-06-11 10:00:00"})
        return _serialize(_EDGE_ROW)

    service = MapsAPIService(query_executor=executor)
    response = get_maps_graph_around(service, "ETH_DEFI")

    assert response.status_code == 200
    assert response.body["node"] == "ETH_DEFI"
    assert len(response.body["inbound"]) == 1
