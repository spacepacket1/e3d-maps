from __future__ import annotations

import json

from api.maps_routes import get_maps_notable
from services.maps_api_service import MapsAPIService


def _serialize_json_each_row(*rows: dict[str, object]) -> bytes:
    return ("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n").encode("utf-8")


def _notable_row(**overrides):
    row = {
        "signal_id": "navsig_01J",
        "signal_type": "capital_migration",
        "asset_scope": ["ETH"],
        "chain_scope": ["ethereum"],
        "confidence": 0.8,
        "question": "Where is ETH heading?",
        "answer": "ETH is rotating into Coinbase.",
        "created_at": "2026-06-08 00:00:00",
        "notability": 80,
    }
    row.update(overrides)
    return row


def test_get_notable_signals_builds_threshold_join_and_ordering_sql():
    seen = {}

    def query_executor(body: bytes) -> bytes:
        seen["sql"] = body.decode("utf-8")
        return _serialize_json_each_row(
            _notable_row(signal_id="navsig_02J", notability=92),
            _notable_row(signal_id="navsig_01J", notability=71),
        )

    service = MapsAPIService(query_executor=query_executor)

    result = service.get_notable_signals(min_score=60, since="2026-06-07 00:00:00", limit=1, offset=2)

    sql = seen["sql"]
    assert "notability >= 60" in sql
    assert "created_at > '2026-06-07 00:00:00'" in sql
    assert "ORDER BY notability DESC, created_at DESC" in sql
    assert "LIMIT 2 OFFSET 2" in sql  # limit + 1 for has_more probe
    assert "LEFT JOIN" in sql
    assert "final_signal_utility_score" in sql
    # Only `limit` items returned; the extra row signals has_more.
    assert len(result.items) == 1
    assert result.items[0]["signal_id"] == "navsig_02J"
    assert result.items[0]["notability"] == 92
    assert result.items[0]["summary"] == "ETH is rotating into Coinbase."
    assert result.has_more is True


def test_get_notable_signals_empty_state_returns_valid_empty_page():
    service = MapsAPIService(query_executor=lambda body: b"")

    result = service.get_notable_signals(min_score=90, limit=50, offset=0)

    assert result.items == ()
    assert result.has_more is False
    assert result.limit == 50


def test_get_maps_notable_route_returns_paginated_body():
    service = MapsAPIService(
        query_executor=lambda body: _serialize_json_each_row(_notable_row())
    )

    response = get_maps_notable(service, min_score=50, limit=10, offset=0)

    assert response.status_code == 200
    assert response.body["status"] == "ok"
    assert response.body["notable"][0]["signal_id"] == "navsig_01J"
    assert response.body["notable"][0]["notability"] == 80
    assert response.body["pagination"]["count"] == 1
    assert response.body["pagination"]["has_more"] is False


def test_get_maps_notable_route_empty_is_not_an_error():
    service = MapsAPIService(query_executor=lambda body: b"")

    response = get_maps_notable(service, min_score=99)

    assert response.status_code == 200
    assert response.body["notable"] == []
    assert response.body["pagination"]["count"] == 0
