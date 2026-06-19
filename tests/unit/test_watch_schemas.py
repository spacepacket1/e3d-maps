from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas import ConsumerAttestation, DraftStatus, WatchDraft, WatchPrediction
from schemas.shared_enums import FlowDirection, FlowMagnitude, OutcomeStatus


def watch_prediction_payload(**overrides):
    payload = {
        "source_signal_id": "navsig_01J",
        "signal_type": "capital_migration",
        "asset_scope": ["ETH"],
        "chain_scope": ["ethereum"],
        "claim": "ETH outflow to Coinbase precedes a price move within 24h.",
        "probability": 0.62,
        "realized_direction_expected": "inflow",
        "magnitude_expected": "high",
        "evaluation_window_hours": 24,
        "model": "gpt-4o",
        "adapter": "",
        "schema_version": "watch_v1",
        "idempotency_key": "abc123",
        "created_at": "2026-06-08T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def watch_draft_payload(**overrides):
    payload = {
        "watch_prediction_id": "wp_01J",
        "headline": "E3D Maps flags $34M ETH to Coinbase",
        "analysis": "Sell-side liquidity is building on Coinbase.",
        "significance": "Material exchange inflow.",
        "x_post": "E3D Maps flagged $34M ETH to Coinbase. Every transaction is traffic. #E3D",
        "linkedin_draft": " ".join(["word"] * 200),
        "model": "gpt-4o",
        "adapter": "",
        "schema_version": "watch_v1",
        "created_at": "2026-06-08T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def consumer_attestation_payload(**overrides):
    payload = {
        "watch_prediction_id": "wp_01J",
        "consumer_id": "trading_agent_alpha",
        "acted": True,
        "observed_direction": "inflow",
        "observed_magnitude": "high",
        "created_at": "2026-06-09T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def test_watch_prediction_validates_clean_payload():
    prediction = WatchPrediction.model_validate(watch_prediction_payload())
    assert prediction.probability == 0.62
    assert prediction.signal_type.value == "capital_migration"
    assert prediction.realized_direction_expected == FlowDirection.INFLOW
    assert prediction.magnitude_expected == FlowMagnitude.HIGH
    assert prediction.status == OutcomeStatus.PENDING
    assert prediction.created_by_agent == "watch_agent"


def test_watch_prediction_rejects_out_of_range_probability():
    with pytest.raises(ValidationError):
        WatchPrediction.model_validate(watch_prediction_payload(probability=1.5))
    with pytest.raises(ValidationError):
        WatchPrediction.model_validate(watch_prediction_payload(probability=-0.1))


def test_watch_prediction_rejects_unknown_signal_type():
    with pytest.raises(ValidationError):
        WatchPrediction.model_validate(watch_prediction_payload(signal_type="not_a_real_type"))


def test_watch_prediction_rejects_empty_claim():
    with pytest.raises(ValidationError):
        WatchPrediction.model_validate(watch_prediction_payload(claim="   "))


def test_watch_prediction_rejects_non_positive_window():
    with pytest.raises(ValidationError):
        WatchPrediction.model_validate(watch_prediction_payload(evaluation_window_hours=0))


def test_watch_draft_validates_and_defaults_status_to_draft():
    draft = WatchDraft.model_validate(watch_draft_payload())
    assert draft.status == DraftStatus.DRAFT
    assert draft.created_by_agent == "watch_draft_generator"
    assert draft.track_record_snapshot == {}
    assert draft.routing == {}


def test_watch_draft_rejects_overlong_x_post():
    with pytest.raises(ValidationError):
        WatchDraft.model_validate(watch_draft_payload(x_post="x" * 281))


def test_watch_draft_rejects_short_linkedin_draft():
    with pytest.raises(ValidationError):
        WatchDraft.model_validate(watch_draft_payload(linkedin_draft="too short"))


def test_consumer_attestation_validates_and_allows_optional_observations():
    attestation = ConsumerAttestation.model_validate(consumer_attestation_payload())
    assert attestation.acted is True
    assert attestation.observed_direction == FlowDirection.INFLOW

    minimal = ConsumerAttestation.model_validate(
        consumer_attestation_payload(observed_direction=None, observed_magnitude=None)
    )
    assert minimal.observed_direction is None
    assert minimal.observed_magnitude is None
    assert minimal.notes == ""
