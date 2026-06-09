from __future__ import annotations

import json
from datetime import UTC, datetime

from jobs.export_training_examples import export_training_examples, write_examples_jsonl
from schemas.navigation_signal import NavigationSignal
from schemas.prediction_outcome import PredictionOutcome
from schemas.signal_utility_score import SignalUtilityScore
from tests.unit.payloads import navigation_signal_payload


def test_export_training_examples_includes_required_fields_and_context():
    signal = NavigationSignal.model_validate(
        navigation_signal_payload(
            id="navsig_export_1",
            confidence=0.78,
        )
    )
    outcome = PredictionOutcome.model_validate(
        {
            "id": "outcome_export_1",
            "navigation_signal_id": "navsig_export_1",
            "route_prediction_id": None,
            "evaluation_window_hours": 24,
            "prediction_accuracy": 0.82,
            "realized_direction": "inflow",
            "realized_magnitude": "moderate",
            "map_prediction_correct": True,
            "notes": "Signal aligned with realized inflow.",
            "created_by_agent": "score_pending_predictions",
            "created_at": "2026-06-09T00:00:00Z",
        }
    )
    utility = SignalUtilityScore.model_validate(
        {
            "id": "utility_export_1",
            "navigation_signal_id": "navsig_export_1",
            "sample_size": 3,
            "prediction_accuracy": 0.82,
            "economic_utility": 0.74,
            "risk_reduction_utility": 0.66,
            "confidence_calibration_error": 0.04,
            "execution_adjusted_utility": 0.71,
            "final_signal_utility_score": 0.76,
            "linked_action_ids": ["action_1"],
            "linked_outcome_ids": ["trade_outcome_1"],
            "created_at": "2026-06-09T00:00:00Z",
        }
    )

    examples = export_training_examples(
        navigation_signals=[signal],
        prediction_outcomes=[outcome],
        utility_scores=[utility],
    )

    assert len(examples) == 1
    example = examples[0]
    assert example["question"] == signal.question
    assert example["answer"] == signal.answer
    assert example["confidence"] == signal.confidence
    assert example["outcome"]["map_prediction_correct"] is True
    assert example["utility_score"]["final_signal_utility_score"] == 0.76
    assert example["context"]["origin"] == "stablecoins"
    assert example["context"]["destination"] == "ETH_DEFI"
    assert example["context"]["evidence"][0]["id"] == "story_123"


def test_export_training_examples_filters_by_utility_score():
    signal = NavigationSignal.model_validate(navigation_signal_payload(id="navsig_export_filter"))
    outcome = PredictionOutcome.model_validate(
        {
            "id": "outcome_export_filter",
            "navigation_signal_id": "navsig_export_filter",
            "route_prediction_id": None,
            "evaluation_window_hours": 24,
            "prediction_accuracy": 0.55,
            "realized_direction": "neutral",
            "realized_magnitude": "low",
            "map_prediction_correct": False,
            "notes": "Mixed evidence.",
            "created_by_agent": "score_pending_predictions",
            "created_at": "2026-06-09T00:00:00Z",
        }
    )
    low_utility = SignalUtilityScore.model_validate(
        {
            "id": "utility_export_filter",
            "navigation_signal_id": "navsig_export_filter",
            "sample_size": 1,
            "prediction_accuracy": 0.55,
            "economic_utility": 0.22,
            "risk_reduction_utility": 0.2,
            "confidence_calibration_error": 0.23,
            "execution_adjusted_utility": 0.24,
            "final_signal_utility_score": 0.25,
            "linked_action_ids": [],
            "linked_outcome_ids": [],
            "created_at": "2026-06-09T00:00:00Z",
        }
    )

    examples = export_training_examples(
        navigation_signals=[signal],
        prediction_outcomes=[outcome],
        utility_scores=[low_utility],
        min_utility_score=0.5,
    )

    assert examples == []


def test_write_examples_jsonl_writes_valid_jsonl(tmp_path):
    examples = [
        {
            "navigation_signal_id": "navsig_export_file",
            "question": "Where is capital likely moving?",
            "context": {"evidence": []},
            "answer": "Toward ETH DeFi.",
            "confidence": 0.68,
            "outcome": {"map_prediction_correct": True},
            "utility_score": None,
            "created_at": "2026-06-08T00:00:00Z",
        },
        {
            "navigation_signal_id": "navsig_export_file_2",
            "question": "Where are hazards forming?",
            "context": {"evidence": []},
            "answer": "Around CEX outflows.",
            "confidence": 0.41,
            "outcome": {"map_prediction_correct": False},
            "utility_score": None,
            "created_at": "2026-06-08T01:00:00Z",
        },
    ]

    output_path = tmp_path / "maps_training_examples.jsonl"
    written_path = write_examples_jsonl(examples, output_path)

    assert written_path == output_path
    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["navigation_signal_id"] == "navsig_export_file"
    assert json.loads(lines[1])["outcome"]["map_prediction_correct"] is False


def test_export_training_examples_uses_latest_outcome_and_utility_score():
    signal = NavigationSignal.model_validate(navigation_signal_payload(id="navsig_export_latest"))
    older_outcome = PredictionOutcome.model_validate(
        {
            "id": "outcome_old",
            "navigation_signal_id": "navsig_export_latest",
            "route_prediction_id": None,
            "evaluation_window_hours": 24,
            "prediction_accuracy": 0.3,
            "realized_direction": "outflow",
            "realized_magnitude": "low",
            "map_prediction_correct": False,
            "notes": "Older decision.",
            "created_by_agent": "score_pending_predictions",
            "created_at": datetime(2026, 6, 9, 0, 0, tzinfo=UTC),
        }
    )
    newer_outcome = PredictionOutcome.model_validate(
        {
            "id": "outcome_new",
            "navigation_signal_id": "navsig_export_latest",
            "route_prediction_id": None,
            "evaluation_window_hours": 24,
            "prediction_accuracy": 0.9,
            "realized_direction": "inflow",
            "realized_magnitude": "high",
            "map_prediction_correct": True,
            "notes": "Latest decision.",
            "created_by_agent": "score_pending_predictions",
            "created_at": datetime(2026, 6, 9, 1, 0, tzinfo=UTC),
        }
    )
    older_utility = SignalUtilityScore.model_validate(
        {
            "id": "utility_old",
            "navigation_signal_id": "navsig_export_latest",
            "sample_size": 1,
            "prediction_accuracy": 0.3,
            "economic_utility": 0.2,
            "risk_reduction_utility": 0.1,
            "confidence_calibration_error": 0.4,
            "execution_adjusted_utility": 0.2,
            "final_signal_utility_score": 0.2,
            "linked_action_ids": [],
            "linked_outcome_ids": [],
            "created_at": datetime(2026, 6, 9, 0, 0, tzinfo=UTC),
        }
    )
    newer_utility = SignalUtilityScore.model_validate(
        {
            "id": "utility_new",
            "navigation_signal_id": "navsig_export_latest",
            "sample_size": 2,
            "prediction_accuracy": 0.9,
            "economic_utility": 0.8,
            "risk_reduction_utility": 0.7,
            "confidence_calibration_error": 0.1,
            "execution_adjusted_utility": 0.76,
            "final_signal_utility_score": 0.79,
            "linked_action_ids": [],
            "linked_outcome_ids": [],
            "created_at": datetime(2026, 6, 9, 1, 0, tzinfo=UTC),
        }
    )

    examples = export_training_examples(
        navigation_signals=[signal],
        prediction_outcomes=[older_outcome, newer_outcome],
        utility_scores=[older_utility, newer_utility],
    )

    assert len(examples) == 1
    assert examples[0]["outcome"]["id"] == "outcome_new"
    assert examples[0]["utility_score"]["id"] == "utility_new"
