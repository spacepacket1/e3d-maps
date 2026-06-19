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
from schemas.shared_enums import ScoringMethod
from schemas.signal_utility_score import SignalUtilityScore
from schemas.watch_prediction import WatchPrediction
from settings import MapsRunnerSettings


def export_training_examples(
    *,
    navigation_signals: Sequence[NavigationSignal],
    prediction_outcomes: Sequence[PredictionOutcome],
    utility_scores: Sequence[SignalUtilityScore],
    watch_predictions: Sequence[WatchPrediction] = (),
    min_utility_score: float | None = None,
    max_utility_score: float | None = None,
    include_disputed: bool = False,
    min_scorer_agreement: float | None = None,
) -> list[dict[str, object]]:
    """Build training examples from scored signals and settled watch predictions.

    By default disputed outcomes (scorer agreement delta > threshold) are
    excluded.  Pass include_disputed=True to override, or set
    min_scorer_agreement to a stricter threshold (e.g. 0.8 means both scorers
    must agree within 0.2).

    Settled watch predictions are included too: each pairs the prediction's
    claim + consumed context + its realized PredictionOutcome (the label) +
    source-signal utility, in the same JSONL shape as signal examples.
    """
    latest_outcomes = _latest_outcomes_by_signal(prediction_outcomes)
    latest_outcomes_by_window = _latest_outcomes_by_signal_window(prediction_outcomes)
    latest_utility_scores = _latest_utility_scores_by_signal(utility_scores)
    examples: list[dict[str, object]] = []

    for signal in navigation_signals:
        signal_id = signal.id or ""
        if not signal_id:
            continue

        outcome = latest_outcomes.get(signal_id)
        if outcome is None:
            continue

        # Quality gate: exclude disputed outcomes unless explicitly included.
        # A disputed outcome has scorer_agreement above the dispute threshold,
        # which produces a blended accuracy with low confidence. We detect it
        # by checking the scoring_method and whether agreement delta is large.
        if not include_disputed and _is_disputed(outcome):
            continue

        # Scorer agreement gate: require that the two scorers agreed within
        # the given tolerance.  scorer_agreement is None for legacy rows (only
        # one scorer ran); those pass through unless min_scorer_agreement is set.
        if min_scorer_agreement is not None and outcome.scorer_agreement is not None:
            required_max_delta = 1.0 - min_scorer_agreement
            if outcome.scorer_agreement > required_max_delta:
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
            # Provenance: how the outcome label was derived (heuristic, quantitative, blended).
            "scoring_method": outcome.scoring_method.value if outcome.scoring_method else "heuristic",
            "created_at": _format_datetime(signal.created_at),
        }
        examples.append(example)

    for prediction in watch_predictions:
        source_signal_id = prediction.source_signal_id or ""
        if not source_signal_id:
            continue

        # Prefer the outcome settled over this prediction's own window; fall back
        # to the latest outcome for the source signal.
        outcome = latest_outcomes_by_window.get(
            (source_signal_id, prediction.evaluation_window_hours)
        ) or latest_outcomes.get(source_signal_id)
        if outcome is None:
            continue
        if not include_disputed and _is_disputed(outcome):
            continue
        if min_scorer_agreement is not None and outcome.scorer_agreement is not None:
            if outcome.scorer_agreement > (1.0 - min_scorer_agreement):
                continue

        utility_score = latest_utility_scores.get(source_signal_id)
        utility_value = utility_score.final_signal_utility_score if utility_score else None
        if min_utility_score is not None and (
            utility_value is None or utility_value < min_utility_score
        ):
            continue
        if max_utility_score is not None and (
            utility_value is None or utility_value > max_utility_score
        ):
            continue

        examples.append(
            {
                "source": "watch_prediction",
                "watch_prediction_id": prediction.id or prediction.idempotency_key,
                "navigation_signal_id": source_signal_id,
                "signal_type": prediction.signal_type.value,
                "adapter": prediction.adapter,
                "question": (
                    f"Given notable signal {source_signal_id}, state the single most "
                    f"falsifiable flow prediction for the next "
                    f"{prediction.evaluation_window_hours} hours."
                ),
                "context": _build_watch_context(prediction),
                "answer": prediction.claim,
                "confidence": prediction.probability,
                "outcome": _model_to_jsonable(outcome),
                "utility_score": _model_to_jsonable(utility_score) if utility_score else None,
                "scoring_method": outcome.scoring_method.value if outcome.scoring_method else "heuristic",
                "created_at": _format_datetime(prediction.created_at),
            }
        )

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
    include_disputed: bool = False,
    min_scorer_agreement: float | None = None,
    dry_run: bool = False,
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
    watch_predictions = _list_watch_predictions(clickhouse_reader, limit=signal_limit)
    signal_ids = [signal.id or "" for signal in signals if signal.id]
    # Watch outcomes are keyed by the source signal id, which may sit outside the
    # adapter-filtered signal set, so union it into the outcome/utility lookups.
    lookup_ids = sorted(
        {sid for sid in signal_ids}
        | {p.source_signal_id for p in watch_predictions if p.source_signal_id}
    )
    examples = export_training_examples(
        navigation_signals=signals,
        prediction_outcomes=_list_prediction_outcomes(
            clickhouse_reader,
            navigation_signal_ids=lookup_ids,
        ),
        utility_scores=_list_signal_utility_scores(
            clickhouse_reader,
            navigation_signal_ids=lookup_ids,
        ),
        watch_predictions=watch_predictions,
        min_utility_score=min_utility_score,
        max_utility_score=max_utility_score,
        include_disputed=include_disputed,
        min_scorer_agreement=min_scorer_agreement,
    )

    target_date = export_date or _utcnow().date()
    destination = Path(output_path) if output_path is not None else _default_output_path(target_date)
    if dry_run:
        return destination
    return write_examples_jsonl(examples, destination)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export Maps training examples as JSONL.")
    parser.add_argument("--signal-limit", type=int, default=1000)
    parser.add_argument("--min-utility-score", type=float, default=None)
    parser.add_argument("--max-utility-score", type=float, default=None)
    parser.add_argument("--adapter", default=None)
    parser.add_argument("--output-path", default=None)
    parser.add_argument(
        "--include-disputed",
        action="store_true",
        default=False,
        help="Include outcomes flagged DISPUTED (large heuristic/quantitative scorer disagreement). Excluded by default.",
    )
    parser.add_argument(
        "--min-scorer-agreement",
        type=float,
        default=None,
        metavar="AGREEMENT",
        help=(
            "Require that 1 - |heuristic_accuracy - quantitative_accuracy| >= AGREEMENT. "
            "E.g. 0.8 means both scorers must agree within 0.2. "
            "Rows where scorer_agreement is None (legacy, single-scorer) pass through."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    run(
        signal_limit=args.signal_limit,
        min_utility_score=args.min_utility_score,
        max_utility_score=args.max_utility_score,
        adapter=args.adapter,
        output_path=args.output_path,
        include_disputed=args.include_disputed,
        min_scorer_agreement=args.min_scorer_agreement,
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


def _build_watch_context(prediction: WatchPrediction) -> dict[str, object]:
    """The context the Watch Agent consumed/produced for this prediction."""
    return {
        "source_signal_id": prediction.source_signal_id,
        "source_prediction_id": prediction.source_prediction_id,
        "signal_type": prediction.signal_type.value,
        "asset_scope": prediction.asset_scope,
        "chain_scope": prediction.chain_scope,
        "realized_direction_expected": prediction.realized_direction_expected.value,
        "magnitude_expected": prediction.magnitude_expected.value,
        "evaluation_window_hours": prediction.evaluation_window_hours,
        "created_by_agent": prediction.created_by_agent,
        "model": prediction.model,
        "adapter": prediction.adapter,
        "schema_version": prediction.schema_version,
        "idempotency_key": prediction.idempotency_key,
    }


def _list_watch_predictions(
    reader: ClickHouseReadClient,
    *,
    limit: int,
) -> list[WatchPrediction]:
    rows = reader.select(
        "SELECT * FROM WatchPredictions "
        "ORDER BY created_at ASC "
        f"LIMIT {max(0, limit)} FORMAT JSONEachRow"
    )
    predictions: list[WatchPrediction] = []
    for row in rows:
        payload = dict(row)
        payload.pop("inserted_at", None)
        if not payload.get("source_prediction_id"):
            payload["source_prediction_id"] = None
        predictions.append(WatchPrediction.model_validate(payload))
    return predictions


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


def _latest_outcomes_by_signal_window(
    outcomes: Sequence[PredictionOutcome],
) -> dict[tuple[str, int], PredictionOutcome]:
    """Latest outcome keyed by (signal_id, evaluation_window_hours).

    Watch predictions over the same source signal but different windows settle
    into distinct outcomes; this lets a watch example pick the outcome for its
    own window rather than the source signal's own outcome.
    """
    latest: dict[tuple[str, int], PredictionOutcome] = {}
    for outcome in outcomes:
        key = (outcome.navigation_signal_id, outcome.evaluation_window_hours)
        current = latest.get(key)
        if current is None or _to_utc(outcome.created_at) >= _to_utc(current.created_at):
            latest[key] = outcome
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


def _is_disputed(outcome: PredictionOutcome) -> bool:
    """Return True when the heuristic and quantitative scorers disagreed enough
    to make the outcome label unreliable for training."""
    if outcome.scoring_method != ScoringMethod.BLENDED:
        return False
    # scorer_agreement is the raw delta; blended outcomes with a large delta
    # are the ones we want to exclude.  Use the same threshold that the scoring
    # job used (importable constant), defaulting to 0.35 if not set.
    from jobs.score_pending_predictions import SCORER_DISPUTE_THRESHOLD  # lazy to avoid circular at module level
    if outcome.scorer_agreement is None:
        return False
    return outcome.scorer_agreement > SCORER_DISPUTE_THRESHOLD


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
