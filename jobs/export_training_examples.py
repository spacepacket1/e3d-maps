from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from api.normalizers import (
    normalize_navigation_signal_row,
    normalize_prediction_outcome_row,
    normalize_signal_utility_score_row,
)
from jobs.compute_signal_utility_scores import ClickHouseReadClient
from schemas.navigation_signal import NavigationSignal
from schemas.prediction_outcome import PredictionOutcome
from schemas.signal_utility_score import SignalUtilityScore
from settings import MapsRunnerSettings


def export_training_examples(
    *,
    navigation_signals: Sequence[NavigationSignal],
    prediction_outcomes: Sequence[PredictionOutcome],
    utility_scores: Sequence[SignalUtilityScore],
    min_utility_score: float | None = None,
    max_utility_score: float | None = None,
) -> list[dict[str, object]]:
    latest_outcomes = _latest_outcomes_by_signal(prediction_outcomes)
    latest_utility_scores = _latest_utility_scores_by_signal(utility_scores)
    examples: list[dict[str, object]] = []

    for signal in navigation_signals:
        signal_id = signal.id or ""
        if not signal_id:
            continue

        outcome = latest_outcomes.get(signal_id)
        if outcome is None:
            continue

        utility_score = latest_utility_scores.get(signal_id)
        utility_value = utility_score.final_signal_utility_score if utility_score else None
        if min_utility_score is not None and (
            utility_value is None or utility_value < min_utility_score
        ):
            continue
        if max_utility_score is not None and (
            utility_value is None or utility_value > max_utility_score
        ):
            continue

        example = {
            "navigation_signal_id": signal_id,
            "signal_type": signal.signal_type,
            "adapter": signal.adapter,
            "question": signal.question,
            "context": _build_context(signal),
            "answer": signal.answer,
            "confidence": signal.confidence,
            "outcome": _model_to_jsonable(outcome),
            "utility_score": _model_to_jsonable(utility_score) if utility_score else None,
            "created_at": _format_datetime(signal.created_at),
        }
        examples.append(example)

    return examples


def write_examples_jsonl(examples: Sequence[dict[str, object]], output_path: str | Path) -> Path:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        for example in examples:
            handle.write(json.dumps(example, separators=(",", ":"), sort_keys=True))
            handle.write("\n")
    return destination


def run(
    *,
    signal_limit: int = 1000,
    min_utility_score: float | None = None,
    max_utility_score: float | None = None,
    adapter: str | None = None,
    output_path: str | Path | None = None,
    export_date: date | None = None,
) -> Path:
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

    signals = _list_navigation_signals(
        clickhouse_reader,
        limit=signal_limit,
        adapter=adapter,
    )
    signal_ids = [signal.id or "" for signal in signals if signal.id]
    examples = export_training_examples(
        navigation_signals=signals,
        prediction_outcomes=_list_prediction_outcomes(
            clickhouse_reader,
            navigation_signal_ids=signal_ids,
        ),
        utility_scores=_list_signal_utility_scores(
            clickhouse_reader,
            navigation_signal_ids=signal_ids,
        ),
        min_utility_score=min_utility_score,
        max_utility_score=max_utility_score,
    )

    target_date = export_date or _utcnow().date()
    destination = Path(output_path) if output_path is not None else _default_output_path(target_date)
    return write_examples_jsonl(examples, destination)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export Maps training examples as JSONL.")
    parser.add_argument("--signal-limit", type=int, default=1000)
    parser.add_argument("--min-utility-score", type=float, default=None)
    parser.add_argument("--max-utility-score", type=float, default=None)
    parser.add_argument("--adapter", default=None)
    parser.add_argument("--output-path", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    run(
        signal_limit=args.signal_limit,
        min_utility_score=args.min_utility_score,
        max_utility_score=args.max_utility_score,
        adapter=args.adapter,
        output_path=args.output_path,
    )
    return 0


def _build_context(signal: NavigationSignal) -> dict[str, object]:
    return {
        "origin": signal.origin,
        "destination": signal.destination,
        "asset_scope": signal.asset_scope,
        "chain_scope": signal.chain_scope,
        "time_horizon_hours": signal.time_horizon_hours,
        "risk_level": signal.risk_level.value,
        "signal_strength": signal.signal_strength.value if signal.signal_strength else None,
        "market_state": signal.market_state.value if signal.market_state else None,
        "supporting_story_ids": signal.supporting_story_ids,
        "supporting_thesis_ids": signal.supporting_thesis_ids,
        "supporting_action_ids": signal.supporting_action_ids,
        "supporting_outcome_ids": signal.supporting_outcome_ids,
        "evidence": [item.model_dump() for item in signal.evidence],
        "recommended_route": (
            signal.recommended_route.model_dump()
            if signal.recommended_route is not None
            else None
        ),
        "recommended_action": signal.recommended_action,
        "created_by_agent": signal.created_by_agent,
        "model": signal.model,
        "adapter": signal.adapter,
        "schema_version": signal.schema_version,
    }


def _list_navigation_signals(
    reader: ClickHouseReadClient,
    *,
    limit: int,
    adapter: str | None = None,
) -> list[NavigationSignal]:
    where_clauses: list[str] = []
    if adapter:
        where_clauses.append(f"adapter = {_sql_quote(adapter)}")

    where_sql = f"WHERE {' AND '.join(where_clauses)} " if where_clauses else ""
    rows = reader.select(
        (
            "SELECT * FROM NavigationSignals "
            f"{where_sql}"
            "ORDER BY created_at ASC "
            f"LIMIT {max(0, limit)} FORMAT JSONEachRow"
        )
    )
    return [normalize_navigation_signal_row(row) for row in rows]


def _list_prediction_outcomes(
    reader: ClickHouseReadClient,
    *,
    navigation_signal_ids: Sequence[str],
) -> list[PredictionOutcome]:
    if not navigation_signal_ids:
        return []
    rows = reader.select(
        (
            "SELECT * FROM PredictionOutcomes "
            f"WHERE navigation_signal_id IN ({_sql_string_list(navigation_signal_ids)}) "
            "FORMAT JSONEachRow"
        )
    )
    return [normalize_prediction_outcome_row(row) for row in rows]


def _list_signal_utility_scores(
    reader: ClickHouseReadClient,
    *,
    navigation_signal_ids: Sequence[str],
) -> list[SignalUtilityScore]:
    if not navigation_signal_ids:
        return []
    rows = reader.select(
        (
            "SELECT * FROM SignalUtilityScores "
            f"WHERE navigation_signal_id IN ({_sql_string_list(navigation_signal_ids)}) "
            "FORMAT JSONEachRow"
        )
    )
    return [normalize_signal_utility_score_row(row) for row in rows]


def _latest_outcomes_by_signal(
    outcomes: Sequence[PredictionOutcome],
) -> dict[str, PredictionOutcome]:
    latest: dict[str, PredictionOutcome] = {}
    for outcome in outcomes:
        current = latest.get(outcome.navigation_signal_id)
        if current is None or _to_utc(outcome.created_at) >= _to_utc(current.created_at):
            latest[outcome.navigation_signal_id] = outcome
    return latest


def _latest_utility_scores_by_signal(
    utility_scores: Sequence[SignalUtilityScore],
) -> dict[str, SignalUtilityScore]:
    latest: dict[str, SignalUtilityScore] = {}
    for score in utility_scores:
        current = latest.get(score.navigation_signal_id)
        if current is None or _to_utc(score.created_at) >= _to_utc(current.created_at):
            latest[score.navigation_signal_id] = score
    return latest


def _default_output_path(export_date: date) -> Path:
    return Path("training/exports") / f"maps_training_examples_{export_date.strftime('%Y%m%d')}.jsonl"


def _model_to_jsonable(model) -> dict[str, object]:
    return json.loads(model.model_dump_json())


def _format_datetime(value: datetime) -> str:
    return _to_utc(value).isoformat().replace("+00:00", "Z")


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _sql_quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _sql_string_list(values: Sequence[str]) -> str:
    return ", ".join(_sql_quote(value) for value in values)
