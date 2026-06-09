from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from jobs.backtest_navigation_predictions import (
    BacktestRecord,
    BacktestReport,
    _build_report,
    _latest_outcomes_by_signal,
    _safe_mean,
)
from schemas.navigation_signal import NavigationSignal
from schemas.prediction_outcome import PredictionOutcome
from schemas.shared_enums import FlowDirection, FlowMagnitude
from tests.unit.payloads import navigation_signal_payload


def make_signal(**overrides) -> NavigationSignal:
    return NavigationSignal.model_validate(navigation_signal_payload(**overrides))


def make_outcome(navigation_signal_id: str, prediction_accuracy: float) -> PredictionOutcome:
    return PredictionOutcome(
        id=f"outcome_{navigation_signal_id}",
        navigation_signal_id=navigation_signal_id,
        evaluation_window_hours=24,
        prediction_accuracy=prediction_accuracy,
        realized_direction=FlowDirection.INFLOW,
        realized_magnitude=FlowMagnitude.MODERATE,
        map_prediction_correct=prediction_accuracy >= 0.6,
        notes="test",
        created_by_agent="test",
        created_at=datetime(2026, 6, 9, tzinfo=UTC),
    )


def test_safe_mean_with_values():
    assert _safe_mean([0.5, 0.7, 0.9]) == pytest.approx(0.7)


def test_safe_mean_with_empty_list():
    assert _safe_mean([]) == 0.0


def test_latest_outcomes_by_signal_returns_most_recent():
    outcome_early = PredictionOutcome(
        id="o1",
        navigation_signal_id="sig_abc",
        evaluation_window_hours=24,
        prediction_accuracy=0.5,
        realized_direction=FlowDirection.INFLOW,
        realized_magnitude=FlowMagnitude.LOW,
        map_prediction_correct=False,
        notes="early",
        created_by_agent="test",
        created_at=datetime(2026, 6, 8, tzinfo=UTC),
    )
    outcome_late = PredictionOutcome(
        id="o2",
        navigation_signal_id="sig_abc",
        evaluation_window_hours=24,
        prediction_accuracy=0.8,
        realized_direction=FlowDirection.INFLOW,
        realized_magnitude=FlowMagnitude.MODERATE,
        map_prediction_correct=True,
        notes="late",
        created_by_agent="test",
        created_at=datetime(2026, 6, 9, tzinfo=UTC),
    )

    result = _latest_outcomes_by_signal([outcome_early, outcome_late])

    assert result["sig_abc"].id == "o2"


def test_build_report_computes_correct_aggregates():
    signal = make_signal(id="navsig_001", confidence=0.70)
    records = [
        BacktestRecord(
            signal_id="navsig_001",
            signal_type="capital_migration",
            created_at=datetime(2026, 6, 8, tzinfo=UTC),
            time_horizon_hours=24,
            confidence=0.70,
            prediction_accuracy=0.80,
            map_prediction_correct=True,
            stored_accuracy=None,
            stored_correct=None,
            accuracy_delta=None,
            notes="matched",
        ),
        BacktestRecord(
            signal_id="navsig_002",
            signal_type="destination_prediction",
            created_at=datetime(2026, 6, 7, tzinfo=UTC),
            time_horizon_hours=24,
            confidence=0.60,
            prediction_accuracy=0.30,
            map_prediction_correct=False,
            stored_accuracy=0.35,
            stored_correct=False,
            accuracy_delta=-0.05,
            notes="did not match",
        ),
    ]

    report = _build_report(
        all_signals=[signal, signal],
        records=records,
        skipped_unsupported=1,
        skipped_window_not_elapsed=2,
    )

    assert isinstance(report, BacktestReport)
    assert report.total_signals == 2
    assert report.scored_signals == 2
    assert report.skipped_unsupported == 1
    assert report.skipped_window_not_elapsed == 2
    assert report.correct_count == 1
    assert report.incorrect_count == 1
    assert report.mean_accuracy == pytest.approx(0.55)
    assert report.mean_confidence == pytest.approx(0.65)
    assert report.calibration_error == pytest.approx(abs(0.55 - 0.65))


def test_build_report_handles_empty_records():
    report = _build_report(
        all_signals=[],
        records=[],
        skipped_unsupported=0,
        skipped_window_not_elapsed=0,
    )

    assert report.scored_signals == 0
    assert report.mean_accuracy == 0.0
    assert report.mean_confidence == 0.0
    assert report.calibration_error == 0.0


def test_backtest_report_to_dict_is_serializable():
    signal = make_signal(id="navsig_001", confidence=0.70)
    records = [
        BacktestRecord(
            signal_id="navsig_001",
            signal_type="capital_migration",
            created_at=datetime(2026, 6, 8, tzinfo=UTC),
            time_horizon_hours=24,
            confidence=0.70,
            prediction_accuracy=0.75,
            map_prediction_correct=True,
            stored_accuracy=0.72,
            stored_correct=True,
            accuracy_delta=0.03,
            notes="matched",
        )
    ]

    report = _build_report(
        all_signals=[signal],
        records=records,
        skipped_unsupported=0,
        skipped_window_not_elapsed=0,
    )
    report_dict = report.to_dict()

    import json
    serialized = json.dumps(report_dict)
    assert '"navsig_001"' in serialized
    assert '"capital_migration"' in serialized
    assert report_dict["correct_count"] == 1
    assert report_dict["records"][0]["accuracy_delta"] == pytest.approx(0.03, abs=0.001)
