from __future__ import annotations

from datetime import UTC, datetime

from jobs.compute_signal_utility_scores import compute_signal_utility_scores
from schemas.navigation_signal import NavigationSignal
from schemas.route_prediction import RoutePrediction
from tests.unit.payloads import navigation_signal_payload, route_prediction_payload


def test_compute_signal_utility_scores_keeps_map_accuracy_separate_from_bad_execution():
    signal = NavigationSignal.model_validate(
        navigation_signal_payload(
            id="navsig_feedback_1",
            confidence=0.82,
            outcome_status="pending",
        )
    )
    action = {
        "id": "action_1",
        "navigation_signal_ids": ["navsig_feedback_1"],
    }
    outcome = {
        "id": "outcome_1",
        "action_id": "action_1",
        "pnl_pct": -12.0,
        "max_drawdown_pct": 3.0,
    }
    verdict = {
        "id": "verdict_1",
        "action_id": "action_1",
        "outcome_id": "outcome_1",
        "map_prediction_correct": True,
        "trade_execution_correct": False,
        "risk_management_correct": True,
    }

    scores = compute_signal_utility_scores(
        navigation_signals=[signal],
        route_predictions=[],
        trading_actions=[action],
        trading_outcomes=[outcome],
        trading_verdicts=[verdict],
        created_at=datetime(2026, 6, 8, tzinfo=UTC),
    )

    assert len(scores) == 1
    score = scores[0]
    assert score.navigation_signal_id == "navsig_feedback_1"
    assert score.linked_action_ids == ["action_1"]
    assert score.linked_outcome_ids == ["outcome_1"]
    assert score.prediction_accuracy == 1.0
    assert score.economic_utility < 0.5
    assert score.execution_adjusted_utility > score.economic_utility
    assert score.risk_reduction_utility == 1.0
    assert score.final_signal_utility_score > 0.6


def test_compute_signal_utility_scores_links_feedback_via_route_predictions():
    signal = NavigationSignal.model_validate(
        navigation_signal_payload(
            id="navsig_route_1",
            confidence=0.7,
            outcome_status="mixed",
        )
    )
    route_prediction = RoutePrediction.model_validate(
        route_prediction_payload(
            id="route_link_1",
            navigation_signal_id="navsig_route_1",
        )
    )
    action = {
        "id": "action_route_1",
        "route_prediction_ids": ["route_link_1"],
    }
    outcome = {
        "id": "outcome_route_1",
        "action_id": "action_route_1",
        "economic_utility": 0.8,
        "prediction_accuracy": 0.75,
    }

    scores = compute_signal_utility_scores(
        navigation_signals=[signal],
        route_predictions=[route_prediction],
        trading_actions=[action],
        trading_outcomes=[outcome],
        trading_verdicts=[],
        created_at=datetime(2026, 6, 8, tzinfo=UTC),
    )

    assert len(scores) == 1
    score = scores[0]
    assert score.linked_action_ids == ["action_route_1"]
    assert score.linked_outcome_ids == ["outcome_route_1"]
    assert score.prediction_accuracy == 0.75
    assert score.economic_utility == 0.8


def test_compute_signal_utility_scores_skips_signals_without_feedback():
    signal = NavigationSignal.model_validate(navigation_signal_payload(id="navsig_empty"))

    scores = compute_signal_utility_scores(
        navigation_signals=[signal],
        route_predictions=[],
        trading_actions=[],
        trading_outcomes=[],
        trading_verdicts=[],
    )

    assert scores == []
