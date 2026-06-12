from __future__ import annotations

import json

from api.maps_routes import get_maps_recommendations
from services.maps_api_service import MapsAPIService
from services.recommendation_engine import (
    STORY_TYPE_SIGNAL_TYPES,
    _compute_score,
    _derive_action,
    synthesize_recommendations,
)
from tests.unit.payloads import navigation_signal_payload, route_prediction_payload
from schemas.navigation_signal import NavigationSignal
from schemas.route_prediction import RoutePrediction


def _make_signal(**overrides) -> NavigationSignal:
    payload = navigation_signal_payload(**overrides)
    return NavigationSignal.model_validate(payload, context={"allow_unknown_signal_types": True})


def _make_route(**overrides) -> RoutePrediction:
    payload = route_prediction_payload(**overrides)
    return RoutePrediction.model_validate(payload, context={"allow_unknown_signal_types": True})


def _serialize(*rows: dict) -> bytes:
    return ("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n").encode()


def _signal_row(**overrides):
    p = navigation_signal_payload(**overrides)
    return {
        "id": p["id"],
        "signal_type": p["signal_type"],
        "question": p["question"],
        "answer": p["answer"],
        "origin": p["origin"],
        "destination": p["destination"],
        "asset_scope": p["asset_scope"],
        "chain_scope": p["chain_scope"],
        "time_horizon_hours": p["time_horizon_hours"],
        "confidence": p["confidence"],
        "risk_level": p["risk_level"],
        "signal_strength": p["signal_strength"],
        "market_state": p["market_state"],
        "supporting_story_ids": p["supporting_story_ids"],
        "supporting_thesis_ids": p["supporting_thesis_ids"],
        "supporting_action_ids": p["supporting_action_ids"],
        "supporting_outcome_ids": p["supporting_outcome_ids"],
        "evidence_json": json.dumps(p["evidence"]),
        "recommended_route_json": json.dumps(p["recommended_route"]),
        "recommended_action": p["recommended_action"],
        "created_by_agent": p["created_by_agent"],
        "model": p["model"],
        "adapter": p["adapter"],
        "schema_version": p["schema_version"],
        "outcome_status": p["outcome_status"],
        "created_at": "2026-06-08 00:00:00",
    }


def _route_row(**overrides):
    p = route_prediction_payload(**overrides)
    return {
        "id": p["id"],
        "navigation_signal_id": p["navigation_signal_id"],
        "route_type": p["route_type"],
        "origin": p["origin"],
        "destination": p["destination"],
        "expected_flow_direction": p["expected_flow_direction"],
        "expected_flow_magnitude": p["expected_flow_magnitude"],
        "time_horizon_hours": p["time_horizon_hours"],
        "confidence": p["confidence"],
        "hazards": p["hazards"],
        "supporting_story_ids": p["supporting_story_ids"],
        "created_by_agent": p["created_by_agent"],
        "model": p["model"],
        "adapter": p["adapter"],
        "schema_version": p["schema_version"],
        "created_at": "2026-06-08 00:00:00",
    }


# --- Unit tests for synthesis logic ---

def test_compute_score_clamps_to_100():
    assert _compute_score(100, 0, 10) == 100


def test_compute_score_clamps_to_zero():
    assert _compute_score(0, 80, 0) == 0


def test_compute_score_typical_values():
    score = _compute_score(78, 35, 1)
    assert 0 <= score <= 100
    assert score == 78 - 8 + 3  # 73


def test_derive_action_hazard_category():
    assert _derive_action({"route_hazard"}, None, "hazard") == "avoid"


def test_derive_action_congestion_category():
    assert _derive_action({"congestion_formation"}, None, "congestion") == "wait"


def test_derive_action_seek_opportunity():
    assert _derive_action({"capital_migration"}, "seek_opportunity", "opportunity") == "increase_attention"


def test_derive_action_grow_capital():
    assert _derive_action({"capital_migration"}, "grow_capital", "opportunity") == "increase_exposure"


def test_derive_action_default_investigate():
    assert _derive_action({"capital_migration"}, None, "opportunity") == "investigate"


def test_synthesize_empty_inputs():
    assert synthesize_recommendations([], [], objective=None) == []


def test_synthesize_single_signal_produces_recommendation():
    signals = [_make_signal()]
    result = synthesize_recommendations(signals, [], objective="seek_opportunity")
    assert len(result) == 1
    rec = result[0]
    assert rec.rank == 1
    assert rec.action == "increase_attention"
    assert 0 <= rec.score <= 100
    assert rec.confidence == 78
    assert rec.story_type == "CapitalRotation"


def test_synthesize_hazard_signal():
    signals = [_make_signal(signal_type="route_hazard", risk_level="high")]
    result = synthesize_recommendations(signals, [], objective=None)
    assert len(result) == 1
    assert result[0].action == "avoid"
    assert "Hazard Alert" in result[0].title


def test_synthesize_respects_max_results():
    signals = [
        _make_signal(id=f"sig_{i}", asset_scope=[f"TOKEN{i}"])
        for i in range(10)
    ]
    result = synthesize_recommendations(signals, [], objective=None, max_results=3)
    assert len(result) == 3
    assert [r.rank for r in result] == [1, 2, 3]


def test_synthesize_links_routes_to_recommendations():
    signals = [_make_signal(id="navsig_01J")]
    routes = [_make_route(navigation_signal_id="navsig_01J", id="route_01J")]
    result = synthesize_recommendations(signals, routes, objective=None)
    assert len(result) == 1
    assert "route_01J" in result[0].supporting_routes


def test_synthesize_ranks_by_score_descending():
    low_conf = _make_signal(id="low", confidence=0.4, asset_scope=["BTC"])
    high_conf = _make_signal(id="high", confidence=0.9, asset_scope=["ETH"])
    result = synthesize_recommendations([low_conf, high_conf], [], objective=None)
    assert result[0].confidence >= result[1].confidence


def test_synthesize_multiple_signals_same_group():
    sig1 = _make_signal(id="s1", confidence=0.8, asset_scope=["ETH"])
    sig2 = _make_signal(id="s2", confidence=0.75, asset_scope=["ETH"])
    result = synthesize_recommendations([sig1, sig2], [], objective=None)
    assert len(result) == 1  # same asset + category → one group
    assert len(result[0].supporting_signals) == 2
    assert any("2 supporting signals" in r for r in result[0].reasoning)


def test_story_type_signal_types_mapping_is_non_empty():
    assert len(STORY_TYPE_SIGNAL_TYPES) > 0
    for key, value in STORY_TYPE_SIGNAL_TYPES.items():
        assert isinstance(key, str)
        assert len(value) > 0


# --- Service-level tests ---

def test_service_get_recommendations_returns_list():
    call_count = [0]

    def query_executor(body: bytes) -> bytes:
        sql = body.decode()
        call_count[0] += 1
        if "NavigationSignals" in sql:
            return _serialize(_signal_row())
        if "RoutePredictions" in sql:
            return _serialize(_route_row())
        return b""

    service = MapsAPIService(query_executor=query_executor)
    result = service.get_recommendations(objective="seek_opportunity", max_results=5)
    assert isinstance(result, list)
    assert call_count[0] == 2  # one for signals, one for routes


def test_service_get_recommendations_filters_by_asset():
    seen = {}

    def query_executor(body: bytes) -> bytes:
        sql = body.decode()
        seen["sql"] = seen.get("sql", [])
        seen["sql"].append(sql)
        if "NavigationSignals" in sql:
            return _serialize(_signal_row())
        return b""

    service = MapsAPIService(query_executor=query_executor)
    service.get_recommendations(asset="ETH")
    signal_sql = next(s for s in seen["sql"] if "NavigationSignals" in s)
    assert "has(asset_scope, 'ETH')" in signal_sql


def test_service_get_recommendations_filters_by_story_type():
    seen_signals = []

    def query_executor(body: bytes) -> bytes:
        sql = body.decode()
        if "NavigationSignals" in sql:
            seen_signals.append(sql)
            return _serialize(_signal_row(signal_type="capital_migration"))
        return b""

    service = MapsAPIService(query_executor=query_executor)
    result = service.get_recommendations(story_type="exchange_flow")
    # exchange_flow covers capital_migration, route_hazard, liquidity_forecast
    # The returned signal is capital_migration which is in that set → should not be filtered out
    assert isinstance(result, list)


def test_service_get_recommendations_story_type_excludes_unrelated_signals():
    def query_executor(body: bytes) -> bytes:
        sql = body.decode()
        if "NavigationSignals" in sql:
            return _serialize(_signal_row(signal_type="congestion_formation"))
        return b""

    service = MapsAPIService(query_executor=query_executor)
    # wallet_accumulation covers capital_migration, destination_prediction, capital_conviction
    # congestion_formation is NOT in that set → filtered out → no recommendations
    result = service.get_recommendations(story_type="wallet_accumulation")
    assert result == []


# --- Route handler tests ---

def test_route_handler_returns_200_with_expected_shape():
    def query_executor(body: bytes) -> bytes:
        if b"NavigationSignals" in body:
            return _serialize(_signal_row())
        return b""

    service = MapsAPIService(query_executor=query_executor)
    response = get_maps_recommendations(service, objective="seek_opportunity", max_results=5)
    assert response.status_code == 200
    assert "generatedAt" in response.body
    assert response.body["objective"] == "seek_opportunity"
    assert isinstance(response.body["recommendations"], list)


def test_route_handler_no_signals_returns_empty_list():
    service = MapsAPIService(query_executor=lambda body: b"")
    response = get_maps_recommendations(service)
    assert response.status_code == 200
    assert response.body["recommendations"] == []
    assert response.body["objective"] is None
