from __future__ import annotations

import json

from jobs.export_training_examples import export_training_examples, write_examples_jsonl
from schemas.prediction_outcome import PredictionOutcome
from schemas.shared_enums import ScoringMethod
from schemas.signal_utility_score import SignalUtilityScore
from schemas.watch_prediction import WatchPrediction


def _watch_prediction(**overrides) -> WatchPrediction:
    payload = {
        "id": "watchpred_01",
        "source_signal_id": "navsig_01J",
        "signal_type": "capital_migration",
        "asset_scope": ["ETH"],
        "chain_scope": ["ethereum"],
        "claim": "ETH keeps flowing into Coinbase over 24 hours.",
        "probability": 0.7,
        "realized_direction_expected": "inflow",
        "magnitude_expected": "high",
        "evaluation_window_hours": 24,
        "model": "gpt-4o",
        "adapter": "base-v0",
        "schema_version": "watch_v1",
        "idempotency_key": "key01",
        "created_at": "2026-06-08T00:00:00Z",
    }
    payload.update(overrides)
    return WatchPrediction.model_validate(payload)


def _outcome(**overrides) -> PredictionOutcome:
    payload = {
        "id": "outcome_navsig_01J_x",
        "navigation_signal_id": "navsig_01J",
        "evaluation_window_hours": 24,
        "prediction_accuracy": 0.82,
        "realized_direction": "inflow",
        "realized_magnitude": "high",
        "map_prediction_correct": True,
        "notes": "settled",
        "created_by_agent": "score_pending_predictions",
        "created_at": "2026-06-09T00:00:00Z",
        "heuristic_accuracy": 0.8,
        "quantitative_accuracy": 0.84,
        "scorer_agreement": 0.04,
        "scoring_method": "blended",
        "consumer_exposure": 0,
        "exogenous_accuracy": 0.82,
    }
    payload.update(overrides)
    return PredictionOutcome.model_validate(payload)


def _utility(**overrides) -> SignalUtilityScore:
    payload = {
        "id": "sus_01",
        "navigation_signal_id": "navsig_01J",
        "sample_size": 10,
        "prediction_accuracy": 0.8,
        "economic_utility": 0.7,
        "risk_reduction_utility": 0.6,
        "confidence_calibration_error": 0.1,
        "execution_adjusted_utility": 0.7,
        "final_signal_utility_score": 0.72,
        "created_at": "2026-06-09T00:00:00Z",
    }
    payload.update(overrides)
    return SignalUtilityScore.model_validate(payload)


def test_settled_watch_prediction_yields_one_labeled_example():
    examples = export_training_examples(
        navigation_signals=[],
        prediction_outcomes=[_outcome()],
        utility_scores=[_utility()],
        watch_predictions=[_watch_prediction()],
    )

    assert len(examples) == 1
    example = examples[0]
    assert example["source"] == "watch_prediction"
    assert example["watch_prediction_id"] == "watchpred_01"
    assert example["answer"] == "ETH keeps flowing into Coinbase over 24 hours."
    # Realized outcome is the label.
    assert example["outcome"]["prediction_accuracy"] == 0.82
    assert example["outcome"]["realized_direction"] == "inflow"
    # Consumed context + utility are present.
    assert example["context"]["realized_direction_expected"] == "inflow"
    assert example["utility_score"]["final_signal_utility_score"] == 0.72
    assert example["confidence"] == 0.7


def test_unsettled_watch_prediction_is_skipped():
    examples = export_training_examples(
        navigation_signals=[],
        prediction_outcomes=[],  # no outcome -> not settled
        utility_scores=[],
        watch_predictions=[_watch_prediction()],
    )
    assert examples == []


def test_disputed_watch_outcome_excluded_by_default_included_on_flag():
    disputed = _outcome(scorer_agreement=0.5, scoring_method="blended")

    excluded = export_training_examples(
        navigation_signals=[],
        prediction_outcomes=[disputed],
        utility_scores=[],
        watch_predictions=[_watch_prediction()],
    )
    assert excluded == []

    included = export_training_examples(
        navigation_signals=[],
        prediction_outcomes=[disputed],
        utility_scores=[],
        watch_predictions=[_watch_prediction()],
        include_disputed=True,
    )
    assert len(included) == 1


def test_watch_example_matches_outcome_for_its_own_window():
    # Same source signal, two outcomes for different windows. The 24h prediction
    # must pick the 24h outcome, not the (more recent) 6h one.
    window_24 = _outcome(
        id="o24", evaluation_window_hours=24, prediction_accuracy=0.82, created_at="2026-06-09T00:00:00Z"
    )
    window_6 = _outcome(
        id="o6", evaluation_window_hours=6, prediction_accuracy=0.30, created_at="2026-06-10T00:00:00Z"
    )

    examples = export_training_examples(
        navigation_signals=[],
        prediction_outcomes=[window_24, window_6],
        utility_scores=[],
        watch_predictions=[_watch_prediction(evaluation_window_hours=24)],
    )

    assert len(examples) == 1
    assert examples[0]["outcome"]["prediction_accuracy"] == 0.82


def test_watch_examples_serialize_to_jsonl(tmp_path):
    examples = export_training_examples(
        navigation_signals=[],
        prediction_outcomes=[_outcome()],
        utility_scores=[_utility()],
        watch_predictions=[_watch_prediction()],
    )
    path = write_examples_jsonl(examples, tmp_path / "watch.jsonl")

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["source"] == "watch_prediction"
    assert parsed["outcome"]["map_prediction_correct"] is True
