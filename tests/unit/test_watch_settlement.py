from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta

from api.maps_routes import post_maps_outcome
from clients.clickhouse_client import ClickHouseClient
from jobs.compute_signal_utility_scores import split_accuracy_by_exposure
from jobs.settle_watch_predictions import (
    count_consumer_exposure,
    settle_watch_prediction,
)
from schemas.consumer_attestation import ConsumerAttestation
from schemas.navigation_signal import NavigationSignal
from schemas.shared_enums import OutcomeStatus
from schemas.watch_prediction import WatchPrediction
from services.maps_api_service import MapsAPIService
from tests.unit.payloads import navigation_signal_payload

PRED_CREATED = datetime(2026, 6, 8, 0, 0, tzinfo=UTC)
AFTER_WINDOW = PRED_CREATED + timedelta(hours=48)


def _source_signal(**overrides) -> NavigationSignal:
    payload = navigation_signal_payload(
        id="navsig_01J",
        origin="stablecoins",
        destination="ETH_DEFI",
        created_at=PRED_CREATED.isoformat(),
        **overrides,
    )
    return NavigationSignal.model_validate(payload)


def _prediction(**overrides) -> WatchPrediction:
    payload = {
        "id": "watchpred_01",
        "source_signal_id": "navsig_01J",
        "signal_type": "capital_migration",
        "asset_scope": ["ETH"],
        "chain_scope": ["ethereum"],
        "claim": "Capital keeps flowing into ETH DeFi over 24 hours.",
        "probability": 0.7,
        "realized_direction_expected": "inflow",
        "magnitude_expected": "high",
        "evaluation_window_hours": 24,
        "model": "gpt-4o",
        "adapter": "base-v0",
        "schema_version": "watch_v1",
        "idempotency_key": "key01",
        "created_at": PRED_CREATED.isoformat(),
    }
    payload.update(overrides)
    return WatchPrediction.model_validate(payload)


def _attestation(**overrides) -> ConsumerAttestation:
    payload = {
        "watch_prediction_id": "watchpred_01",
        "consumer_id": "trading_agent_alpha",
        "acted": True,
        "created_at": (PRED_CREATED + timedelta(hours=2)).isoformat(),
    }
    payload.update(overrides)
    return ConsumerAttestation.model_validate(payload)


_SUPPORTING_STORY = {
    "id": "story_1",
    "ts_created": (PRED_CREATED + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
    "summary": "Stablecoins flowing into ETH_DEFI; accumulation and inflow rising.",
    "origin": "stablecoins",
    "destination": "ETH_DEFI",
}


def test_settlement_produces_a_linked_outcome_over_prediction_window():
    decision = settle_watch_prediction(
        prediction=_prediction(),
        source_signal=_source_signal(),
        stories=[_SUPPORTING_STORY],
        exchange_flows=[],
        stablecoin_activity=[],
        attestations=[],
        now=AFTER_WINDOW,
    )

    outcome = decision.outcome
    # Linked to the source signal, evaluated over the prediction's window.
    assert outcome.navigation_signal_id == "navsig_01J"
    assert outcome.evaluation_window_hours == 24
    assert 0.0 <= outcome.prediction_accuracy <= 1.0
    assert decision.status in set(OutcomeStatus)


def test_consumer_exposure_counts_acted_attestations_before_window_close():
    window_end = PRED_CREATED + timedelta(hours=24)
    attestations = [
        _attestation(consumer_id="a", acted=True),  # in window, acted -> counts
        _attestation(consumer_id="b", acted=False),  # not acted -> excluded
        _attestation(
            consumer_id="c",
            acted=True,
            created_at=(PRED_CREATED + timedelta(hours=30)).isoformat(),  # after window -> excluded
        ),
        _attestation(consumer_id="d", watch_prediction_id="other", acted=True),  # other prediction
    ]

    exposure = count_consumer_exposure(_prediction(), attestations, window_end=window_end)
    assert exposure == 1


def test_zero_exposure_populates_exogenous_accuracy_only():
    decision = settle_watch_prediction(
        prediction=_prediction(),
        source_signal=_source_signal(),
        stories=[_SUPPORTING_STORY],
        exchange_flows=[],
        stablecoin_activity=[],
        attestations=[],  # nobody acted
        now=AFTER_WINDOW,
    )

    outcome = decision.outcome
    assert outcome.consumer_exposure == 0
    assert outcome.exogenous_accuracy == outcome.prediction_accuracy
    assert outcome.induced_accuracy is None


def test_positive_exposure_populates_induced_accuracy_only():
    decision = settle_watch_prediction(
        prediction=_prediction(),
        source_signal=_source_signal(),
        stories=[_SUPPORTING_STORY],
        exchange_flows=[],
        stablecoin_activity=[],
        attestations=[_attestation(), _attestation(consumer_id="beta")],
        now=AFTER_WINDOW,
    )

    outcome = decision.outcome
    assert outcome.consumer_exposure == 2
    assert outcome.induced_accuracy == outcome.prediction_accuracy
    assert outcome.exogenous_accuracy is None


def test_split_accuracy_by_exposure_helper():
    assert split_accuracy_by_exposure(0.8, 0) == (0.8, None)
    assert split_accuracy_by_exposure(0.8, 3) == (None, 0.8)
    # clamps out-of-range input
    assert split_accuracy_by_exposure(1.5, 0) == (1.0, None)


def test_ingest_consumer_attestation_validates_and_writes():
    output = io.StringIO()
    writer = ClickHouseClient(dry_run=True, output=output)
    service = MapsAPIService(clickhouse_writer=writer)

    attestation = service.ingest_consumer_attestation(
        {
            "watch_prediction_id": "watchpred_01",
            "consumer_id": "trading_agent_alpha",
            "acted": True,
            "observed_direction": "inflow",
            "created_at": "2026-06-09T00:00:00Z",
        }
    )

    assert attestation.acted is True
    printed = json.loads(output.getvalue())
    assert printed["table"] == "ConsumerAttestations"
    assert printed["rows"][0]["acted"] == 1
    assert printed["rows"][0]["observed_direction"] == "inflow"


def test_post_maps_outcome_route_returns_201_and_400():
    writer = ClickHouseClient(dry_run=True, output=io.StringIO())
    service = MapsAPIService(clickhouse_writer=writer)

    ok = post_maps_outcome(
        service,
        {
            "watch_prediction_id": "watchpred_01",
            "consumer_id": "agent",
            "acted": True,
            "created_at": "2026-06-09T00:00:00Z",
        },
    )
    assert ok.status_code == 201
    assert ok.body["status"] == "ok"
    assert ok.body["attestation"]["watch_prediction_id"] == "watchpred_01"

    bad = post_maps_outcome(service, {"consumer_id": "agent"})  # missing required fields
    assert bad.status_code == 400
    assert bad.body["error"] == "invalid_attestation"
