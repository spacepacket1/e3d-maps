from __future__ import annotations

import io
import json

import pytest
from pydantic import ValidationError

from clients.clickhouse_client import ClickHouseClient, ClickHouseClientError
from schemas.prediction_outcome import PredictionOutcome
from schemas.signal_utility_score import SignalUtilityScore
from schemas.traffic_state import TrafficState
from tests.unit.payloads import navigation_signal_payload, route_prediction_payload


def traffic_state_payload(**overrides):
    payload = {
        "id": "traffic_01J",
        "scope": "global",
        "market_state": "transitioning",
        "dominant_flows": [
            {"origin": "stablecoins", "destination": "ETH_DEFI", "strength": "strong"}
        ],
        "congestion_zones": ["CEX"],
        "hazards": ["bridge_risk"],
        "top_destinations": [{"destination": "ETH_DEFI", "confidence": 0.72}],
        "created_by_agent": "maps_runner",
        "created_at": "2026-06-08T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def prediction_outcome_payload(**overrides):
    payload = {
        "id": "outcome_01J",
        "navigation_signal_id": "navsig_01J",
        "route_prediction_id": "route_01J",
        "evaluation_window_hours": 24,
        "prediction_accuracy": 0.67,
        "realized_direction": "inflow",
        "realized_magnitude": "moderate",
        "map_prediction_correct": True,
        "notes": "Signal aligned with exchange and stablecoin flow evidence.",
        "created_by_agent": "score_pending_predictions",
        "created_at": "2026-06-08T12:00:00Z",
    }
    payload.update(overrides)
    return payload


def signal_utility_score_payload(**overrides):
    payload = {
        "id": "sus_01J",
        "navigation_signal_id": "navsig_01J",
        "sample_size": 14,
        "prediction_accuracy": 0.71,
        "economic_utility": 0.66,
        "risk_reduction_utility": 0.59,
        "confidence_calibration_error": 0.11,
        "execution_adjusted_utility": 0.63,
        "final_signal_utility_score": 0.64,
        "linked_action_ids": ["action_123"],
        "linked_outcome_ids": ["outcome_456"],
        "created_at": "2026-06-08T12:00:00Z",
    }
    payload.update(overrides)
    return payload


def test_insert_navigation_signal_dry_run_prints_rows():
    output = io.StringIO()
    client = ClickHouseClient(dry_run=True, output=output)

    inserted = client.insert_navigation_signal(navigation_signal_payload())

    assert inserted == 1
    printed = json.loads(output.getvalue())
    assert printed["table"] == "NavigationSignals"
    assert printed["rows"][0]["signal_type"] == "capital_migration"
    assert printed["rows"][0]["created_at"] == "2026-06-08 00:00:00"
    assert json.loads(printed["rows"][0]["evidence_json"])[0]["id"] == "story_123"


def test_insert_route_predictions_supports_batch_and_serializes_payload():
    captured = {}

    def request_executor(body: bytes) -> bytes:
        captured["body"] = body.decode("utf-8")
        return b""

    client = ClickHouseClient(request_executor=request_executor)

    inserted = client.insert_route_predictions(
        [route_prediction_payload(id="route_01J"), route_prediction_payload(id="route_02J")]
    )

    assert inserted == 2
    lines = captured["body"].strip().splitlines()
    assert lines[0] == "INSERT INTO RoutePredictions FORMAT JSONEachRow"
    assert json.loads(lines[1])["id"] == "route_01J"
    assert json.loads(lines[2])["id"] == "route_02J"


def test_insert_traffic_state_serializes_nested_lists_to_json_strings():
    output = io.StringIO()
    client = ClickHouseClient(dry_run=True, output=output)

    inserted = client.insert_traffic_state(TrafficState.model_validate(traffic_state_payload()))

    assert inserted == 1
    printed = json.loads(output.getvalue())
    row = printed["rows"][0]
    assert json.loads(row["dominant_flows_json"])[0]["destination"] == "ETH_DEFI"
    assert json.loads(row["top_destinations_json"])[0]["confidence"] == 0.72
    assert row["model"] == ""


def test_insert_prediction_outcome_converts_boolean_to_uint8():
    output = io.StringIO()
    client = ClickHouseClient(dry_run=True, output=output)

    inserted = client.insert_prediction_outcome(prediction_outcome_payload())

    assert inserted == 1
    printed = json.loads(output.getvalue())
    assert printed["rows"][0]["map_prediction_correct"] == 1
    assert printed["rows"][0]["schema_version"] == ""


def test_update_navigation_signal_outcome_status_issues_mutation_query():
    captured = {}

    def request_executor(body: bytes) -> bytes:
        captured["body"] = body.decode("utf-8")
        return b""

    client = ClickHouseClient(request_executor=request_executor)

    updated = client.update_navigation_signal_outcome_status("navsig_01J", "correct")

    assert updated == 1
    assert captured["body"] == (
        "ALTER TABLE NavigationSignals "
        "UPDATE outcome_status = 'correct' "
        "WHERE id = 'navsig_01J'"
    )


def test_insert_signal_utility_score_accepts_validated_model():
    output = io.StringIO()
    client = ClickHouseClient(dry_run=True, output=output)
    score = SignalUtilityScore.model_validate(signal_utility_score_payload())

    inserted = client.insert_signal_utility_score(score)

    assert inserted == 1
    printed = json.loads(output.getvalue())
    assert printed["rows"][0]["final_signal_utility_score"] == 0.64


def test_insert_navigation_signal_rejects_invalid_payload():
    client = ClickHouseClient(dry_run=True, output=io.StringIO())

    with pytest.raises(ValidationError):
        client.insert_navigation_signal(navigation_signal_payload(confidence=1.5))


def test_request_errors_are_wrapped():
    def request_executor(body: bytes) -> bytes:
        raise ClickHouseClientError("boom")

    client = ClickHouseClient(request_executor=request_executor)

    with pytest.raises(ClickHouseClientError):
        client.insert_prediction_outcome(PredictionOutcome.model_validate(prediction_outcome_payload()))


def test_recent_signal_exists_returns_false_in_dry_run():
    client = ClickHouseClient(dry_run=True, output=io.StringIO())
    assert client.recent_signal_exists("capital_migration", "stablecoins", "ETH_DEFI") is False


def test_recent_signal_exists_returns_true_when_count_nonzero():
    def request_executor(body: bytes) -> bytes:
        return b'{"cnt": 3}\n'

    client = ClickHouseClient(request_executor=request_executor)
    assert client.recent_signal_exists("capital_migration", "stablecoins", "ETH_DEFI") is True


def test_recent_signal_exists_returns_false_when_count_zero():
    def request_executor(body: bytes) -> bytes:
        return b'{"cnt": 0}\n'

    client = ClickHouseClient(request_executor=request_executor)
    assert client.recent_signal_exists("capital_migration", "stablecoins", "ETH_DEFI") is False


def test_recent_signal_exists_sends_correct_query():
    captured = {}

    def request_executor(body: bytes) -> bytes:
        captured["query"] = body.decode("utf-8")
        return b'{"cnt": 0}\n'

    client = ClickHouseClient(request_executor=request_executor)
    client.recent_signal_exists("route_hazard", "ETH_DEFI", "SOLANA_L2", within_hours=6)

    query = captured["query"]
    assert "signal_type = 'route_hazard'" in query
    assert "origin = 'ETH_DEFI'" in query
    assert "destination = 'SOLANA_L2'" in query
    assert "INTERVAL 6 HOUR" in query


def test_recent_signal_exists_returns_false_on_request_error():
    from urllib.error import URLError

    def request_executor(body: bytes) -> bytes:
        raise URLError("connection refused")

    client = ClickHouseClient(request_executor=request_executor)
    assert client.recent_signal_exists("capital_migration", "stablecoins", "ETH_DEFI") is False


def test_recent_signal_exists_escapes_single_quotes():
    captured = {}

    def request_executor(body: bytes) -> bytes:
        captured["query"] = body.decode("utf-8")
        return b'{"cnt": 0}\n'

    client = ClickHouseClient(request_executor=request_executor)
    client.recent_signal_exists("O'Brien", "a", "b")

    # The single quote must be escaped so it can't terminate the string literal
    assert "O\\'Brien" in captured["query"]
