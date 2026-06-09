from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable, Sequence

from api.normalizers import normalize_navigation_signal_row, normalize_prediction_outcome_row
from clients.e3d_api_client import E3DAPIClient
from jobs.compute_signal_utility_scores import ClickHouseReadClient
from jobs.score_pending_predictions import (
    SUPPORTED_SIGNAL_TYPES,
    OutcomeDecision,
    _evaluation_window_end,
    _to_utc,
    _utcnow,
    score_prediction,
)
from schemas.navigation_signal import NavigationSignal
from schemas.prediction_outcome import PredictionOutcome
from settings import MapsRunnerSettings


@dataclass(frozen=True)
class BacktestRecord:
    signal_id: str
    signal_type: str
    created_at: datetime
    time_horizon_hours: int
    confidence: float
    prediction_accuracy: float
    map_prediction_correct: bool
    stored_accuracy: float | None
    stored_correct: bool | None
    accuracy_delta: float | None
    notes: str


@dataclass(frozen=True)
class BacktestReport:
    total_signals: int
    scored_signals: int
    skipped_unsupported: int
    skipped_window_not_elapsed: int
    correct_count: int
    incorrect_count: int
    mean_accuracy: float
    mean_confidence: float
    calibration_error: float
    records: tuple[BacktestRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_signals": self.total_signals,
            "scored_signals": self.scored_signals,
            "skipped_unsupported": self.skipped_unsupported,
            "skipped_window_not_elapsed": self.skipped_window_not_elapsed,
            "correct_count": self.correct_count,
            "incorrect_count": self.incorrect_count,
            "mean_accuracy": round(self.mean_accuracy, 4),
            "mean_confidence": round(self.mean_confidence, 4),
            "calibration_error": round(self.calibration_error, 4),
            "records": [
                {
                    "signal_id": r.signal_id,
                    "signal_type": r.signal_type,
                    "created_at": r.created_at.isoformat(),
                    "time_horizon_hours": r.time_horizon_hours,
                    "confidence": round(r.confidence, 4),
                    "prediction_accuracy": round(r.prediction_accuracy, 4),
                    "map_prediction_correct": r.map_prediction_correct,
                    "stored_accuracy": round(r.stored_accuracy, 4) if r.stored_accuracy is not None else None,
                    "stored_correct": r.stored_correct,
                    "accuracy_delta": round(r.accuracy_delta, 4) if r.accuracy_delta is not None else None,
                    "notes": r.notes,
                }
                for r in self.records
            ],
        }


def run(
    *,
    signal_limit: int = 500,
    context_limit: int = 100,
    lookback_days: int = 30,
    now: datetime | None = None,
) -> BacktestReport:
    """Replay historical NavigationSignals and re-score them with the rubric.

    Fetches signals from the lookback window, re-applies the scoring rubric
    against post-hoc evidence from the E3D API, and compares to stored
    PredictionOutcomes where available. Returns a BacktestReport summarizing
    prediction accuracy and calibration error.
    """
    settings = MapsRunnerSettings.from_env()
    clickhouse_reader = ClickHouseReadClient(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        database=settings.clickhouse_database,
        username=settings.clickhouse_username,
        password=settings.clickhouse_password,
        secure=settings.clickhouse_secure,
        timeout=settings.clickhouse_timeout,
    )
    e3d_client = E3DAPIClient(
        base_url=settings.e3d_base_url,
        api_prefix=settings.e3d_api_prefix,
        api_key=settings.e3d_api_key,
        timeout=settings.clickhouse_timeout,
    )

    current_time = _utcnow() if now is None else _to_utc(now)
    lookback_start = current_time - timedelta(days=lookback_days)

    all_signals = _list_signals_in_window(
        clickhouse_reader,
        start=lookback_start,
        end=current_time,
        limit=signal_limit,
    )

    skipped_unsupported = 0
    skipped_window_not_elapsed = 0
    records: list[BacktestRecord] = []

    signal_ids = [s.id for s in all_signals if s.id]
    stored_outcomes_by_signal = _latest_outcomes_by_signal(
        _list_prediction_outcomes(clickhouse_reader, navigation_signal_ids=signal_ids)
    )
    routes_by_signal = _group_routes_by_signal(
        _list_route_predictions(clickhouse_reader, navigation_signal_ids=signal_ids)
    )

    for signal in all_signals:
        if not signal.id or signal.signal_type not in SUPPORTED_SIGNAL_TYPES:
            skipped_unsupported += 1
            continue

        window_end = _evaluation_window_end(signal)
        if window_end > current_time:
            skipped_window_not_elapsed += 1
            continue

        window_start = _to_utc(signal.created_at)

        try:
            decision = score_prediction(
                signal=signal,
                route_predictions=routes_by_signal.get(signal.id, ()),
                stories=e3d_client.get_stories_within_window(
                    start_time=window_start,
                    end_time=window_end,
                    max_items=context_limit,
                ),
                exchange_flows=e3d_client.get_exchange_flows_within_window(
                    start_time=window_start,
                    end_time=window_end,
                    max_items=context_limit,
                ),
                stablecoin_activity=e3d_client.get_stablecoin_activity_within_window(
                    start_time=window_start,
                    end_time=window_end,
                    max_items=context_limit,
                ),
                created_at=current_time,
            )
        except Exception:
            skipped_unsupported += 1
            continue

        stored = stored_outcomes_by_signal.get(signal.id)
        stored_accuracy = stored.prediction_accuracy if stored is not None else None
        stored_correct = stored.map_prediction_correct if stored is not None else None
        accuracy_delta = (
            decision.outcome.prediction_accuracy - stored_accuracy
            if stored_accuracy is not None
            else None
        )

        records.append(
            BacktestRecord(
                signal_id=signal.id,
                signal_type=signal.signal_type,
                created_at=_to_utc(signal.created_at),
                time_horizon_hours=signal.time_horizon_hours,
                confidence=signal.confidence,
                prediction_accuracy=decision.outcome.prediction_accuracy,
                map_prediction_correct=decision.outcome.map_prediction_correct,
                stored_accuracy=stored_accuracy,
                stored_correct=stored_correct,
                accuracy_delta=accuracy_delta,
                notes=decision.outcome.notes,
            )
        )

    return _build_report(
        all_signals=all_signals,
        records=records,
        skipped_unsupported=skipped_unsupported,
        skipped_window_not_elapsed=skipped_window_not_elapsed,
    )


def _build_report(
    *,
    all_signals: list[NavigationSignal],
    records: list[BacktestRecord],
    skipped_unsupported: int,
    skipped_window_not_elapsed: int,
) -> BacktestReport:
    correct = [r for r in records if r.map_prediction_correct]
    incorrect = [r for r in records if not r.map_prediction_correct]
    mean_accuracy = _safe_mean([r.prediction_accuracy for r in records])
    mean_confidence = _safe_mean([r.confidence for r in records])
    calibration_error = abs(mean_accuracy - mean_confidence) if records else 0.0

    return BacktestReport(
        total_signals=len(all_signals),
        scored_signals=len(records),
        skipped_unsupported=skipped_unsupported,
        skipped_window_not_elapsed=skipped_window_not_elapsed,
        correct_count=len(correct),
        incorrect_count=len(incorrect),
        mean_accuracy=mean_accuracy,
        mean_confidence=mean_confidence,
        calibration_error=calibration_error,
        records=tuple(records),
    )


def _list_signals_in_window(
    reader: ClickHouseReadClient,
    *,
    start: datetime,
    end: datetime,
    limit: int,
) -> list[NavigationSignal]:
    start_str = start.strftime("%Y-%m-%d %H:%M:%S")
    end_str = end.strftime("%Y-%m-%d %H:%M:%S")
    rows = reader.select(
        (
            "SELECT * FROM NavigationSignals "
            f"WHERE created_at >= '{start_str}' AND created_at < '{end_str}' "
            "ORDER BY created_at ASC "
            f"LIMIT {max(0, limit)} FORMAT JSONEachRow"
        )
    )
    return [normalize_navigation_signal_row(row) for row in rows]


def _list_route_predictions(
    reader: ClickHouseReadClient,
    *,
    navigation_signal_ids: list[str],
) -> list[Any]:
    if not navigation_signal_ids:
        return []
    from api.normalizers import normalize_route_prediction_row
    from jobs.score_pending_predictions import _sql_string_list

    rows = reader.select(
        (
            "SELECT * FROM RoutePredictions "
            f"WHERE navigation_signal_id IN ({_sql_string_list(navigation_signal_ids)}) "
            "FORMAT JSONEachRow"
        )
    )
    return [normalize_route_prediction_row(row) for row in rows]


def _list_prediction_outcomes(
    reader: ClickHouseReadClient,
    *,
    navigation_signal_ids: list[str],
) -> list[PredictionOutcome]:
    if not navigation_signal_ids:
        return []
    from jobs.score_pending_predictions import _sql_string_list

    rows = reader.select(
        (
            "SELECT * FROM PredictionOutcomes "
            f"WHERE navigation_signal_id IN ({_sql_string_list(navigation_signal_ids)}) "
            "FORMAT JSONEachRow"
        )
    )
    return [normalize_prediction_outcome_row(row) for row in rows]


def _latest_outcomes_by_signal(
    outcomes: Iterable[PredictionOutcome],
) -> dict[str, PredictionOutcome]:
    latest: dict[str, PredictionOutcome] = {}
    for outcome in outcomes:
        current = latest.get(outcome.navigation_signal_id)
        if current is None or _to_utc(outcome.created_at) > _to_utc(current.created_at):
            latest[outcome.navigation_signal_id] = outcome
    return latest


def _group_routes_by_signal(
    route_predictions: Iterable[Any],
) -> dict[str, tuple]:
    grouped: dict[str, list] = {}
    for route in route_predictions:
        grouped.setdefault(route.navigation_signal_id, []).append(route)
    return {key: tuple(value) for key, value in grouped.items()}


def _safe_mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backtest NavigationSignal predictions.")
    parser.add_argument("--signal-limit", type=int, default=500)
    parser.add_argument("--context-limit", type=int, default=100)
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--output", help="Write JSON report to this path.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = run(
        signal_limit=args.signal_limit,
        context_limit=args.context_limit,
        lookback_days=args.lookback_days,
    )
    report_dict = report.to_dict()
    report_json = json.dumps(report_dict, indent=2)

    if args.output:
        from pathlib import Path
        Path(args.output).write_text(report_json, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(report_json)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
