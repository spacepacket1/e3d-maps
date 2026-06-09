from __future__ import annotations

import json

from api.maps_routes import get_maps_hazards, get_maps_signal, get_maps_signals, get_maps_state
from api.story_types_routes import get_story_type, get_story_types
from services.maps_api_service import MapsAPIService
from tests.unit.payloads import (
    navigation_signal_payload,
    route_prediction_payload,
    story_type_definition_payload,
)
from tests.unit.test_clickhouse_client import traffic_state_payload


def _serialize_json_each_row(*rows: dict[str, object]) -> bytes:
    return ("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n").encode("utf-8")


def _navigation_signal_row(**overrides):
    payload = navigation_signal_payload(**overrides)
    return {
        "id": payload["id"],
        "signal_type": payload["signal_type"],
        "question": payload["question"],
        "answer": payload["answer"],
        "origin": payload["origin"],
        "destination": payload["destination"],
        "asset_scope": payload["asset_scope"],
        "chain_scope": payload["chain_scope"],
        "time_horizon_hours": payload["time_horizon_hours"],
        "confidence": payload["confidence"],
        "risk_level": payload["risk_level"],
        "signal_strength": payload["signal_strength"],
        "market_state": payload["market_state"],
        "supporting_story_ids": payload["supporting_story_ids"],
        "supporting_thesis_ids": payload["supporting_thesis_ids"],
        "supporting_action_ids": payload["supporting_action_ids"],
        "supporting_outcome_ids": payload["supporting_outcome_ids"],
        "evidence_json": json.dumps(payload["evidence"]),
        "recommended_route_json": json.dumps(payload["recommended_route"]),
        "recommended_action": payload["recommended_action"],
        "created_by_agent": payload["created_by_agent"],
        "model": payload["model"],
        "adapter": payload["adapter"],
        "schema_version": payload["schema_version"],
        "outcome_status": payload["outcome_status"],
        "created_at": "2026-06-08 00:00:00",
    }


def _route_prediction_row(**overrides):
    payload = route_prediction_payload(**overrides)
    return {
        "id": payload["id"],
        "navigation_signal_id": payload["navigation_signal_id"],
        "route_type": payload["route_type"],
        "origin": payload["origin"],
        "destination": payload["destination"],
        "expected_flow_direction": payload["expected_flow_direction"],
        "expected_flow_magnitude": payload["expected_flow_magnitude"],
        "time_horizon_hours": payload["time_horizon_hours"],
        "confidence": payload["confidence"],
        "hazards": payload["hazards"],
        "supporting_story_ids": payload["supporting_story_ids"],
        "created_by_agent": payload["created_by_agent"],
        "model": payload["model"],
        "adapter": payload["adapter"],
        "schema_version": payload["schema_version"],
        "created_at": "2026-06-08 00:00:00",
    }


def _traffic_state_row(**overrides):
    payload = traffic_state_payload(**overrides)
    return {
        "id": payload["id"],
        "scope": payload["scope"],
        "market_state": payload["market_state"],
        "dominant_flows_json": json.dumps(payload["dominant_flows"]),
        "congestion_zones": payload["congestion_zones"],
        "hazards": payload["hazards"],
        "top_destinations_json": json.dumps(payload["top_destinations"]),
        "created_by_agent": payload["created_by_agent"],
        "created_at": "2026-06-08 00:00:00",
    }


def _story_type_row(**overrides):
    payload = story_type_definition_payload(**overrides)
    return {
        "story_type": payload["story_type"],
        "display_name": payload["display_name"],
        "category": payload["category"],
        "human_meaning": payload["human_meaning"],
        "agent_meaning": payload["agent_meaning"],
        "inputs": payload["inputs"],
        "outputs": payload["outputs"],
        "example_questions": payload["example_questions"],
        "related_navigation_signal_types": payload["related_navigation_signal_types"],
        "schema_version": payload["schema_version"],
        "created_at": "2026-06-08 00:00:00",
        "updated_at": "2026-06-08 12:00:00",
    }


def test_get_latest_state_normalizes_clickhouse_json_columns():
    seen = {}

    def query_executor(body: bytes) -> bytes:
        seen["sql"] = body.decode("utf-8")
        return _serialize_json_each_row(_traffic_state_row())

    service = MapsAPIService(query_executor=query_executor)

    state = service.get_latest_state()

    assert "FROM TrafficStates" in seen["sql"]
    assert state is not None
    assert state.market_state == "transitioning"
    assert state.dominant_flows[0].destination == "ETH_DEFI"


def test_list_signals_applies_filters_and_pagination():
    seen = {}

    def query_executor(body: bytes) -> bytes:
        seen["sql"] = body.decode("utf-8")
        return _serialize_json_each_row(
            _navigation_signal_row(id="navsig_02J"),
            _navigation_signal_row(id="navsig_01J"),
        )

    service = MapsAPIService(query_executor=query_executor)

    result = service.list_signals(
        signal_type="capital_migration",
        asset="ETH",
        chain="ethereum",
        time_horizon_hours=24,
        min_confidence=0.7,
        limit=1,
        offset=5,
    )

    assert "signal_type = 'capital_migration'" in seen["sql"]
    assert "has(asset_scope, 'ETH')" in seen["sql"]
    assert "has(chain_scope, 'ethereum')" in seen["sql"]
    assert "time_horizon_hours = 24" in seen["sql"]
    assert "confidence >= 0.7" in seen["sql"]
    assert "LIMIT 2 OFFSET 5" in seen["sql"]
    assert len(result.items) == 1
    assert result.items[0].id == "navsig_02J"
    assert result.has_more is True


def test_get_signal_returns_none_when_missing():
    service = MapsAPIService(query_executor=lambda body: b"")
    assert service.get_signal("missing") is None


def test_list_routes_returns_route_predictions():
    service = MapsAPIService(
        query_executor=lambda body: _serialize_json_each_row(_route_prediction_row())
    )

    result = service.list_routes(limit=10, offset=0)

    assert len(result.items) == 1
    assert result.items[0].route_type == "destination_prediction"


def test_list_hazards_filters_to_hazard_signal_types():
    seen = {}

    def query_executor(body: bytes) -> bytes:
        seen["sql"] = body.decode("utf-8")
        return _serialize_json_each_row(_navigation_signal_row(signal_type="route_hazard"))

    service = MapsAPIService(query_executor=query_executor)

    result = service.list_hazards(limit=10, offset=0)

    assert "signal_type IN ('route_hazard', 'route_closure')" in seen["sql"]
    assert result.items[0].signal_type == "route_hazard"


def test_story_type_queries_return_latest_definitions():
    seen = {}

    def query_executor(body: bytes) -> bytes:
        sql = body.decode("utf-8")
        seen.setdefault("sql", []).append(sql)
        if "WHERE story_type =" in sql:
            return _serialize_json_each_row(_story_type_row())
        return _serialize_json_each_row(_story_type_row(), _story_type_row(story_type="exchange_flow"))

    service = MapsAPIService(query_executor=query_executor)

    listing = service.list_story_types(limit=10, offset=0)
    detail = service.get_story_type("capital_migration")

    assert "LIMIT 1 BY story_type" in seen["sql"][0]
    assert len(listing.items) == 2
    assert listing.items[0].story_type == "capital_migration"
    assert detail is not None
    assert detail.updated_at.isoformat() == "2026-06-08T12:00:00+00:00"


def test_route_handlers_return_expected_payload_shapes():
    state_service = MapsAPIService(query_executor=lambda body: _serialize_json_each_row(_traffic_state_row()))
    state_response = get_maps_state(state_service)
    assert state_response.status_code == 200
    assert state_response.body["state"]["scope"] == "global"

    signal_service = MapsAPIService(
        query_executor=lambda body: _serialize_json_each_row(
            _navigation_signal_row(id="navsig_02J"),
            _navigation_signal_row(id="navsig_01J"),
        )
    )
    signals_response = get_maps_signals(signal_service, limit=1, offset=0)
    assert signals_response.status_code == 200
    assert signals_response.body["pagination"]["has_more"] is True

    signal_detail_response = get_maps_signal(signal_service, "navsig_02J")
    assert signal_detail_response.status_code == 200
    assert signal_detail_response.body["signal"]["id"] == "navsig_02J"

    hazards_response = get_maps_hazards(signal_service, limit=1, offset=0)
    assert hazards_response.status_code == 200
    assert hazards_response.body["pagination"]["count"] == 1

    story_type_service = MapsAPIService(query_executor=lambda body: _serialize_json_each_row(_story_type_row()))
    story_types_response = get_story_types(story_type_service, limit=10, offset=0)
    assert story_types_response.status_code == 200
    assert story_types_response.body["story_types"][0]["updated_at"] == "2026-06-08T12:00:00Z"

    story_type_response = get_story_type(story_type_service, "capital_migration")
    assert story_type_response.status_code == 200
    assert story_type_response.body["story_type"]["story_type"] == "capital_migration"
