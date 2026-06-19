from __future__ import annotations

import json

from api.maps_routes import get_agent_draft, get_agent_drafts, get_agent_prediction
from services.maps_api_service import MapsAPIService


def _serialize_json_each_row(*rows: dict[str, object]) -> bytes:
    return ("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n").encode("utf-8")


# ── Fixtures ──────────────────────────────────────────────────────────────────

_LINKEDIN_DRAFT = " ".join(["capital"] * 150)  # exactly 150 words — satisfies validator


def _watch_draft_row(**overrides):
    row = {
        "id": "draft_01J",
        "watch_prediction_id": "pred_01J",
        "headline": "ETH DeFi capital migration expected over next 24 hours",
        "analysis": "On-chain flows suggest sustained capital movement into ETH DeFi venues.",
        "significance": "High — conviction is elevated across multiple story types.",
        "x_post": "ETH DeFi flows are picking up. Watch closely. #DeFi #Ethereum",
        "linkedin_draft": _LINKEDIN_DRAFT,
        "track_record_snapshot": json.dumps({"accuracy": 0.78}),
        "routing": json.dumps({"destination": "ETH_DEFI"}),
        "status": "draft",
        "created_by_agent": "watch_draft_generator",
        "model": "qwen",
        "adapter": "base-v0",
        "schema_version": "1.0",
        "created_at": "2026-06-19 10:00:00",
    }
    row.update(overrides)
    return row


def _watch_prediction_row(**overrides):
    row = {
        "id": "pred_01J",
        "source_signal_id": "navsig_01J",
        "source_prediction_id": "",
        "signal_type": "capital_migration",
        "asset_scope": ["ETH", "AAVE"],
        "chain_scope": ["ethereum"],
        "claim": "Capital will migrate from stablecoins to ETH DeFi within 24 hours.",
        "probability": 0.72,
        "realized_direction_expected": "inflow",
        "magnitude_expected": "moderate",
        "evaluation_window_hours": 24,
        "status": "pending",
        "created_by_agent": "watch_agent",
        "model": "qwen",
        "adapter": "base-v0",
        "schema_version": "1.0",
        "idempotency_key": "navsig_01J:capital_migration:2026-06-19",
        "created_at": "2026-06-19 10:00:00",
    }
    row.update(overrides)
    return row


# ── list_watch_drafts / get_agent_drafts ─────────────────────────────────────

def test_list_watch_drafts_returns_paginated_result():
    seen = {}

    def query_executor(body: bytes) -> bytes:
        seen["sql"] = body.decode("utf-8")
        return _serialize_json_each_row(
            _watch_draft_row(id="draft_02J"),
            _watch_draft_row(id="draft_01J"),
        )

    service = MapsAPIService(query_executor=query_executor)
    result = service.list_watch_drafts(limit=1, offset=0)

    assert "FROM WatchDrafts" in seen["sql"]
    assert "ORDER BY created_at DESC, id DESC" in seen["sql"]
    assert len(result.items) == 1
    assert result.items[0].id == "draft_02J"
    assert result.has_more is True


def test_get_agent_drafts_returns_200_with_paginated_body():
    service = MapsAPIService(
        query_executor=lambda body: _serialize_json_each_row(_watch_draft_row())
    )
    response = get_agent_drafts(service, limit=10, offset=0)

    assert response.status_code == 200
    assert response.body["status"] == "ok"
    assert "drafts" in response.body
    assert response.body["pagination"]["count"] == 1
    assert response.body["drafts"][0]["id"] == "draft_01J"


# ── get_watch_draft / get_agent_draft ────────────────────────────────────────

def test_get_watch_draft_returns_model_when_found():
    service = MapsAPIService(
        query_executor=lambda body: _serialize_json_each_row(_watch_draft_row())
    )
    draft = service.get_watch_draft("draft_01J")

    assert draft is not None
    assert draft.id == "draft_01J"
    assert draft.headline == "ETH DeFi capital migration expected over next 24 hours"
    assert draft.track_record_snapshot == {"accuracy": 0.78}
    assert draft.routing == {"destination": "ETH_DEFI"}


def test_get_watch_draft_returns_none_when_missing():
    service = MapsAPIService(query_executor=lambda body: b"")
    assert service.get_watch_draft("missing") is None


def test_get_agent_draft_returns_200_with_draft():
    service = MapsAPIService(
        query_executor=lambda body: _serialize_json_each_row(_watch_draft_row())
    )
    response = get_agent_draft(service, "draft_01J")

    assert response.status_code == 200
    assert response.body["status"] == "ok"
    assert response.body["draft"]["id"] == "draft_01J"
    assert response.body["draft"]["headline"] == "ETH DeFi capital migration expected over next 24 hours"


def test_get_agent_draft_returns_404_when_missing():
    service = MapsAPIService(query_executor=lambda body: b"")
    response = get_agent_draft(service, "missing")

    assert response.status_code == 404
    assert response.body == {"status": "not_found", "error": "draft_not_found"}


# ── get_watch_prediction / get_agent_prediction ──────────────────────────────

def test_get_watch_prediction_returns_model_when_found():
    service = MapsAPIService(
        query_executor=lambda body: _serialize_json_each_row(_watch_prediction_row())
    )
    prediction = service.get_watch_prediction("pred_01J")

    assert prediction is not None
    assert prediction.id == "pred_01J"
    assert prediction.source_prediction_id is None  # "" → None
    assert prediction.probability == 0.72
    assert prediction.status.value == "pending"


def test_get_watch_prediction_returns_none_when_missing():
    service = MapsAPIService(query_executor=lambda body: b"")
    assert service.get_watch_prediction("missing") is None


def test_get_agent_prediction_returns_200_with_prediction():
    service = MapsAPIService(
        query_executor=lambda body: _serialize_json_each_row(_watch_prediction_row())
    )
    response = get_agent_prediction(service, "pred_01J")

    assert response.status_code == 200
    assert response.body["status"] == "ok"
    assert response.body["prediction"]["id"] == "pred_01J"
    assert response.body["prediction"]["signal_type"] == "capital_migration"


def test_get_agent_prediction_returns_404_when_missing():
    service = MapsAPIService(query_executor=lambda body: b"")
    response = get_agent_prediction(service, "missing")

    assert response.status_code == 404
    assert response.body == {"status": "not_found", "error": "prediction_not_found"}


def test_watch_draft_json_string_columns_round_trip():
    """Verify that JSON-string columns (track_record_snapshot, routing) survive the
    normalizer and come back as dicts."""
    row = _watch_draft_row(
        track_record_snapshot=json.dumps({"wins": 10, "losses": 3}),
        routing=json.dumps({"chain": "ethereum", "protocol": "aave"}),
    )
    service = MapsAPIService(
        query_executor=lambda body: _serialize_json_each_row(row)
    )
    draft = service.get_watch_draft("draft_01J")

    assert draft is not None
    assert draft.track_record_snapshot == {"wins": 10, "losses": 3}
    assert draft.routing == {"chain": "ethereum", "protocol": "aave"}


def test_watch_draft_empty_json_string_columns_normalise_to_empty_dict():
    """Empty-string JSON columns should normalise to {} without raising."""
    row = _watch_draft_row(track_record_snapshot="", routing="")
    service = MapsAPIService(
        query_executor=lambda body: _serialize_json_each_row(row)
    )
    draft = service.get_watch_draft("draft_01J")

    assert draft is not None
    assert draft.track_record_snapshot == {}
    assert draft.routing == {}
