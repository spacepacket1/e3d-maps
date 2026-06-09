from __future__ import annotations

from datetime import UTC, datetime

import pytest

from jobs.score_pending_predictions import score_prediction
from schemas.navigation_signal import NavigationSignal
from schemas.route_prediction import RoutePrediction
from schemas.shared_enums import FlowDirection, FlowMagnitude, OutcomeStatus
from tests.unit.payloads import navigation_signal_payload, route_prediction_payload


def test_score_prediction_scores_elapsed_signal_with_windowed_evidence():
    signal = navigation_signal_payload(
        id="navsig_score_1",
        created_at="2026-06-08T00:00:00Z",
        time_horizon_hours=24,
    )
    route_prediction = route_prediction_payload(
        id="route_score_1",
        navigation_signal_id="navsig_score_1",
        created_at="2026-06-08T00:00:00Z",
        expected_flow_direction="inflow",
        expected_flow_magnitude="moderate",
    )

    decision = score_prediction(
        signal=NavigationSignal.model_validate(signal),
        route_predictions=[RoutePrediction.model_validate(route_prediction)],
        stories=[
            {
                "id": "story_match",
                "story_type": "capital_migration",
                "origin": "stablecoins",
                "destination": "ETH_DEFI",
                "summary": "Stablecoins rotated into ETH DeFi.",
                "timestamp": "2026-06-08T06:00:00Z",
            }
        ],
        exchange_flows=[
            {
                "id": "flow_match",
                "destination": "ETH_DEFI",
                "direction": "inflow",
                "magnitude": "high",
                "summary": "Exchange flow moved into ETH DeFi.",
                "timestamp": "2026-06-08T10:00:00Z",
            }
        ],
        stablecoin_activity=[
            {
                "id": "stable_match",
                "summary": "Stablecoin minting and inflow accelerated for deployment.",
                "direction": "inflow",
                "timestamp": "2026-06-08T11:00:00Z",
            }
        ],
        created_at=datetime(2026, 6, 9, 0, 0, tzinfo=UTC),
    )

    assert decision.outcome.navigation_signal_id == "navsig_score_1"
    assert decision.outcome.route_prediction_id == "route_score_1"
    assert decision.outcome.prediction_accuracy == pytest.approx(1.0)
    assert decision.outcome.realized_direction is FlowDirection.INFLOW
    assert decision.outcome.realized_magnitude is FlowMagnitude.HIGH
    assert decision.outcome.map_prediction_correct is True
    assert decision.status is OutcomeStatus.CORRECT
    assert "story_match" in decision.outcome.notes
    assert "flow_match" in decision.outcome.notes
    assert "stable_match" in decision.outcome.notes


def test_score_prediction_excludes_future_and_untimestamped_records():
    signal = navigation_signal_payload(
        id="navsig_score_2",
        created_at="2026-06-08T00:00:00Z",
        time_horizon_hours=24,
    )

    decision = score_prediction(
        signal=NavigationSignal.model_validate(signal),
        route_predictions=[],
        stories=[
            {
                "id": "story_future",
                "origin": "stablecoins",
                "destination": "ETH_DEFI",
                "summary": "Future data should not count.",
                "timestamp": "2026-06-09T03:00:00Z",
            },
            {
                "id": "story_missing_time",
                "origin": "stablecoins",
                "destination": "ETH_DEFI",
                "summary": "Missing timestamp should be skipped.",
            },
        ],
        exchange_flows=[],
        stablecoin_activity=[],
        created_at=datetime(2026, 6, 9, 0, 0, tzinfo=UTC),
    )

    assert decision.outcome.prediction_accuracy == 0.1
    assert decision.outcome.realized_direction is FlowDirection.NEUTRAL
    assert decision.status is OutcomeStatus.INCORRECT
    assert "story_future" not in decision.outcome.notes
    assert "stories=1" in decision.outcome.notes
