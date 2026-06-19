from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable, Sequence

from api.normalizers import normalize_navigation_signal_row
from clients.clickhouse_client import ClickHouseClient
from clients.e3d_api_client import E3DAPIClient
from jobs.compute_signal_utility_scores import ClickHouseReadClient, split_accuracy_by_exposure
from jobs.score_pending_predictions import (
    OutcomeDecision,
    _list_stories_from_ch,
    score_prediction,
)
from schemas.consumer_attestation import ConsumerAttestation
from schemas.navigation_signal import NavigationSignal
from schemas.route_prediction import RoutePrediction
from schemas.watch_prediction import WatchPrediction
from settings import MapsRunnerSettings


def count_consumer_exposure(
    prediction: WatchPrediction,
    attestations: Iterable[ConsumerAttestation],
    *,
    window_end: datetime,
) -> int:
    """Number of consumers that acted on this prediction before its window closed.

    This is the raw input to ``PredictionOutcome.consumer_exposure`` and, in
    turn, the exogenous/induced reflexivity split.
    """
    prediction_id = prediction.id or prediction.idempotency_key
    window_end_utc = _to_utc(window_end)
    count = 0
    for attestation in attestations:
        if (attestation.watch_prediction_id or "") != prediction_id:
            continue
        if not attestation.acted:
            continue
        if _to_utc(attestation.created_at) <= window_end_utc:
            count += 1
    return count


def settle_watch_prediction(
    *,
    prediction: WatchPrediction,
    source_signal: NavigationSignal,
    stories: Iterable[dict[str, Any]],
    exchange_flows: Iterable[dict[str, Any]],
    stablecoin_activity: Iterable[dict[str, Any]],
    attestations: Iterable[ConsumerAttestation] = (),
    now: datetime | None = None,
) -> OutcomeDecision:
    """Settle one watch prediction into a PredictionOutcome via the existing
    scoring pipeline.

    Reuses ``score_prediction`` against on-chain ground truth. The outcome is
    tied to the source signal (``navigation_signal_id = source_signal_id``) but
    evaluated over the *prediction's* window and graded against the *watch
    prediction's own* expected direction/magnitude — not the source signal's —
    so the public track record honestly reflects the Watch Agent's calls and the
    distill labels pair each claim with its realized outcome. We grade the claim
    by feeding it through the scorer's existing route-prediction seam rather than
    modifying the scorer. ``consumer_exposure`` is counted from attestations, and
    the exogenous/induced split is populated from it.
    """
    scored_at = _utcnow() if now is None else _to_utc(now)
    window_end = _to_utc(prediction.created_at) + timedelta(
        hours=max(0, prediction.evaluation_window_hours)
    )
    exposure = count_consumer_exposure(prediction, attestations, window_end=window_end)

    # Evaluate over the prediction's window while keeping the outcome linked to
    # the source signal. We copy the signal so the existing window math
    # (created_at + time_horizon_hours) reflects the prediction.
    scoring_signal = source_signal.model_copy(
        update={
            "id": prediction.source_signal_id,
            "time_horizon_hours": prediction.evaluation_window_hours,
            "created_at": prediction.created_at,
        }
    )

    decision = score_prediction(
        signal=scoring_signal,
        route_predictions=(_synthesize_claim_route(prediction, scoring_signal),),
        stories=stories,
        exchange_flows=exchange_flows,
        stablecoin_activity=stablecoin_activity,
        created_at=scored_at,
        consumer_exposure=exposure,
    )

    exogenous_accuracy, induced_accuracy = split_accuracy_by_exposure(
        decision.outcome.prediction_accuracy, exposure
    )
    outcome = decision.outcome.model_copy(
        update={
            "exogenous_accuracy": exogenous_accuracy,
            "induced_accuracy": induced_accuracy,
        }
    )
    return OutcomeDecision(outcome=outcome, status=decision.status)


def _synthesize_claim_route(
    prediction: WatchPrediction,
    source_signal: NavigationSignal,
) -> RoutePrediction:
    """A throwaway RoutePrediction encoding the watch claim's expected direction.

    The flow-family scorer derives its predicted direction from a route
    prediction, so passing this routes the existing machinery to grade the watch
    prediction's own claim. Its ``id`` is None so it never appears as the
    outcome's ``route_prediction_id``.
    """
    origin = source_signal.origin or (
        prediction.chain_scope[0] if prediction.chain_scope else "unknown"
    )
    destination = source_signal.destination or (
        prediction.asset_scope[0] if prediction.asset_scope else origin
    )
    return RoutePrediction(
        id=None,
        navigation_signal_id=prediction.source_signal_id,
        route_type=prediction.signal_type.value,
        origin=origin,
        destination=destination,
        expected_flow_direction=prediction.realized_direction_expected,
        expected_flow_magnitude=prediction.magnitude_expected,
        time_horizon_hours=prediction.evaluation_window_hours,
        confidence=prediction.probability,
        created_at=prediction.created_at,
    )


# ── job entrypoint ──────────────────────────────────────────────────────────────


def run(
    *,
    prediction_limit: int = 200,
    context_limit: int = 100,
    dry_run: bool = False,
    now: datetime | None = None,
) -> int:
    settings = MapsRunnerSettings.from_env()
    reader = ClickHouseReadClient(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        database=settings.clickhouse_database,
        username=settings.clickhouse_username,
        password=settings.clickhouse_password,
        secure=settings.clickhouse_secure,
        timeout=settings.clickhouse_timeout,
    )
    writer = ClickHouseClient(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        database=settings.clickhouse_database,
        username=settings.clickhouse_username,
        password=settings.clickhouse_password,
        secure=settings.clickhouse_secure,
        timeout=settings.clickhouse_timeout,
        dry_run=dry_run,
    )
    e3d_client = E3DAPIClient(
        base_url=settings.e3d_base_url,
        api_prefix=settings.e3d_api_prefix,
        api_key=settings.e3d_api_key,
        timeout=settings.clickhouse_timeout,
    )

    current_time = _utcnow() if now is None else _to_utc(now)
    predictions = _list_pending_watch_predictions(reader, limit=prediction_limit)
    elapsed = [
        prediction
        for prediction in predictions
        if _window_end(prediction) <= current_time
    ]
    if not elapsed:
        return 0

    source_ids = sorted({p.source_signal_id for p in elapsed if p.source_signal_id})
    signals_by_id = {
        signal.id or "": signal
        for signal in _list_navigation_signals(reader, ids=source_ids)
    }
    attestations = _list_attestations(
        reader,
        prediction_ids=[p.id or p.idempotency_key for p in elapsed],
    )

    decisions: list[OutcomeDecision] = []
    for prediction in elapsed:
        source_signal = signals_by_id.get(prediction.source_signal_id)
        if source_signal is None:
            continue
        window_start = _to_utc(prediction.created_at)
        window_end = _window_end(prediction)
        decision = settle_watch_prediction(
            prediction=prediction,
            source_signal=source_signal,
            stories=_list_stories_from_ch(
                reader,
                window_start=window_start,
                window_end=window_end,
                limit=context_limit,
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
            attestations=attestations,
            now=current_time,
        )
        decisions.append(decision)

    if decisions:
        writer.insert_prediction_outcomes([decision.outcome for decision in decisions])
    return len(decisions)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Settle pending WatchPredictions into outcomes.")
    parser.add_argument("--prediction-limit", type=int, default=200)
    parser.add_argument("--context-limit", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    settled = run(
        prediction_limit=args.prediction_limit,
        context_limit=args.context_limit,
        dry_run=args.dry_run,
    )
    return 0 if settled >= 0 else 1


# ── ClickHouse reads + row normalization ────────────────────────────────────────


def _list_pending_watch_predictions(
    reader: ClickHouseReadClient,
    *,
    limit: int,
) -> list[WatchPrediction]:
    rows = reader.select(
        "SELECT * FROM WatchPredictions "
        "WHERE status = 'pending' "
        "ORDER BY created_at ASC "
        f"LIMIT {max(0, limit)} FORMAT JSONEachRow"
    )
    return [_normalize_watch_prediction_row(row) for row in rows]


def _list_navigation_signals(
    reader: ClickHouseReadClient,
    *,
    ids: Sequence[str],
) -> list[NavigationSignal]:
    if not ids:
        return []
    id_list = ", ".join(_sql_string(i) for i in ids if i)
    rows = reader.select(
        f"SELECT * FROM NavigationSignals WHERE id IN ({id_list}) FORMAT JSONEachRow"
    )
    return [normalize_navigation_signal_row(row) for row in rows]


def _list_attestations(
    reader: ClickHouseReadClient,
    *,
    prediction_ids: Sequence[str],
) -> list[ConsumerAttestation]:
    ids = [i for i in prediction_ids if i]
    if not ids:
        return []
    id_list = ", ".join(_sql_string(i) for i in ids)
    rows = reader.select(
        f"SELECT * FROM ConsumerAttestations WHERE watch_prediction_id IN ({id_list}) FORMAT JSONEachRow"
    )
    return [normalize_consumer_attestation_row(row) for row in rows]


def _normalize_watch_prediction_row(row: dict[str, Any]) -> WatchPrediction:
    payload = dict(row)
    payload.pop("inserted_at", None)
    if not payload.get("source_prediction_id"):
        payload["source_prediction_id"] = None
    return WatchPrediction.model_validate(payload)


def normalize_consumer_attestation_row(row: dict[str, Any]) -> ConsumerAttestation:
    payload = dict(row)
    payload.pop("inserted_at", None)
    payload["acted"] = bool(payload.get("acted"))
    for key in ("observed_direction", "observed_magnitude"):
        if not payload.get(key):
            payload[key] = None
    return ConsumerAttestation.model_validate(payload)


def _window_end(prediction: WatchPrediction) -> datetime:
    return _to_utc(prediction.created_at) + timedelta(
        hours=max(0, prediction.evaluation_window_hours)
    )


def _sql_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _utcnow() -> datetime:
    return datetime.now(UTC)


# Re-exported for callers that build attestation context.
__all__ = [
    "count_consumer_exposure",
    "settle_watch_prediction",
    "normalize_consumer_attestation_row",
    "run",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
