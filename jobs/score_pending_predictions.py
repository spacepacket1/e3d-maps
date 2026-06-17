from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable, Sequence

from api.normalizers import (
    normalize_navigation_signal_row,
    normalize_prediction_outcome_row,
    normalize_route_prediction_row,
)
from clients.clickhouse_client import ClickHouseClient
from clients.e3d_api_client import E3DAPIClient
from jobs.compute_signal_utility_scores import ClickHouseReadClient
from jobs.scoring.families import SUPPORTED_SIGNAL_TYPES, SignalFamily, family_for
from jobs.scoring.quantitative_scorer import score as quantitative_score
from schemas.navigation_signal import NavigationSignal
from schemas.prediction_outcome import PredictionOutcome
from schemas.route_prediction import RoutePrediction
from schemas.shared_enums import FlowDirection, FlowMagnitude, OutcomeStatus, ScoringMethod
from settings import MapsRunnerSettings

# SUPPORTED_SIGNAL_TYPES is now the union of every family with an honest
# realization measure (flow + hazard + congestion); it is imported from
# jobs.scoring.families and re-exported here for backtest compatibility.

# Heuristic rubric weights — configurable so they can be tuned from backtests
# (MAPS-1203) without changing code.  Loaded from env at import time; override
# in .env or the test environment as needed.
import os as _os

RUBRIC_WEIGHT_STORIES: float = float(_os.environ.get("MAPS_RUBRIC_WEIGHT_STORIES", "0.4"))
RUBRIC_WEIGHT_EXCHANGE: float = float(_os.environ.get("MAPS_RUBRIC_WEIGHT_EXCHANGE", "0.3"))
RUBRIC_WEIGHT_STABLECOIN: float = float(_os.environ.get("MAPS_RUBRIC_WEIGHT_STABLECOIN", "0.2"))
RUBRIC_WEIGHT_NO_CONTRADICTION: float = float(_os.environ.get("MAPS_RUBRIC_WEIGHT_NO_CONTRADICTION", "0.1"))
RUBRIC_PENALTY_PER_CONTRADICTION: float = float(_os.environ.get("MAPS_RUBRIC_PENALTY_PER_CONTRADICTION", "0.3"))

# When |heuristic_accuracy - quantitative_accuracy| exceeds this threshold the
# outcome is flagged DISPUTED and excluded from training export by default.
SCORER_DISPUTE_THRESHOLD: float = float(_os.environ.get("MAPS_SCORER_DISPUTE_THRESHOLD", "0.35"))

# --- Hazard-family rubric (route_hazard / route_closure) ---------------------
# A hazard "realizes" when adverse evidence materializes: danger-flavored stories
# about the route's asset/destination, plus capital fleeing the route (measured
# quantitatively as net outflow). These launch defaults will be replaced by
# backtested weights (MAPS-1203), same as the flow rubric above.
HAZARD_WEIGHT_DANGER: float = 0.7
HAZARD_WEIGHT_NO_RECOVERY: float = 0.1
HAZARD_PENALTY_RECOVERY: float = 0.3
HAZARD_DANGER_KEYWORDS: tuple[str, ...] = (
    "exploit", "hack", "drain", "rug", "blacklist", "distribution", "dump",
    "liquidat", "depeg", "scam", "wash", "exit", "closure", "sell", "outflow",
    "withdraw", "risk", "unsafe", "freeze", "honeypot",
)
HAZARD_RECOVERY_KEYWORDS: tuple[str, ...] = (
    "recovery", "recovered", "resumed", "stabiliz", "all clear", "inflow",
    "accumulation", "safe", "resolved", "reopen",
)

# --- Congestion-family rubric (congestion_formation) -------------------------
# Congestion "realizes" when crowding persists rather than dissipating: activity
# stories about the zone, plus sustained on-chain activity referencing it.
CONGESTION_WEIGHT_CROWDING: float = 0.7
CONGESTION_WEIGHT_NO_DISSIPATION: float = 0.1
CONGESTION_PENALTY_DISSIPATION: float = 0.3
CONGESTION_ACTIVITY_KEYWORDS: tuple[str, ...] = (
    "surge", "spike", "crowd", "congest", "concentrat", "activity", "volume",
    "airdrop", "holders", "rush", "frenzy", "inflow", "accumulation",
)
CONGESTION_DISSIPATE_KEYWORDS: tuple[str, ...] = (
    "cooldown", "quiet", "subsid", "decline", "slowdown", "outflow", "exit",
    "dispers", "unwind",
)


@dataclass(frozen=True)
class OutcomeDecision:
    outcome: PredictionOutcome
    status: OutcomeStatus


@dataclass(frozen=True)
class EvidenceBucket:
    supporting_stories: tuple[dict[str, Any], ...]
    contradicting_stories: tuple[dict[str, Any], ...]
    supporting_exchange_flows: tuple[dict[str, Any], ...]
    contradicting_exchange_flows: tuple[dict[str, Any], ...]
    supporting_stablecoin_activity: tuple[dict[str, Any], ...]
    contradicting_stablecoin_activity: tuple[dict[str, Any], ...]
    skipped_stories: int = 0
    skipped_exchange_flows: int = 0
    skipped_stablecoin_activity: int = 0


@dataclass(frozen=True)
class FamilyResult:
    """Per-family scoring output, normalized so the outcome-building code is
    family-agnostic. Each family computes its own two independent witnesses
    (heuristic + quantitative), the blended accuracy, the realized
    direction/magnitude, a notes body, and support/contradiction counts."""

    heuristic_accuracy: float
    quantitative_accuracy: float
    prediction_accuracy: float
    realized_direction: FlowDirection
    realized_magnitude: FlowMagnitude
    support_count: int
    contradiction_count: int
    notes_body: str
    route_prediction_id: str | None = None


def score_prediction(
    *,
    signal: NavigationSignal,
    route_predictions: Iterable[RoutePrediction],
    stories: Iterable[dict[str, Any]],
    exchange_flows: Iterable[dict[str, Any]],
    stablecoin_activity: Iterable[dict[str, Any]],
    created_at: datetime | None = None,
    consumer_exposure: int = 0,
) -> OutcomeDecision:
    scored_at = _utcnow() if created_at is None else _to_utc(created_at)

    # Materialise iterables once so they can be passed to every scorer.
    stories_list = list(stories)
    exchange_flows_list = list(exchange_flows)
    stablecoin_activity_list = list(stablecoin_activity)

    # Dispatch to the family-appropriate dual-witness scorer. Each signal type
    # realizes differently, so they cannot share one rubric without producing
    # dishonest labels. UNSCORABLE types are filtered out upstream in run() and
    # fall through to the flow scorer only if score_prediction is called directly.
    family = family_for(signal.signal_type)
    if family is SignalFamily.HAZARD:
        result = _score_hazard_family(
            signal=signal,
            stories=stories_list,
            exchange_flows=exchange_flows_list,
            stablecoin_activity=stablecoin_activity_list,
        )
    elif family is SignalFamily.CONGESTION:
        result = _score_congestion_family(
            signal=signal,
            stories=stories_list,
            exchange_flows=exchange_flows_list,
            stablecoin_activity=stablecoin_activity_list,
        )
    else:
        result = _score_flow_family(
            signal=signal,
            route_predictions=route_predictions,
            stories=stories_list,
            exchange_flows=exchange_flows_list,
            stablecoin_activity=stablecoin_activity_list,
        )

    # --- Dispute detection (family-agnostic) ---
    scorer_agreement = abs(result.heuristic_accuracy - result.quantitative_accuracy)
    disputed = scorer_agreement > SCORER_DISPUTE_THRESHOLD
    prediction_accuracy = result.prediction_accuracy
    scoring_method = ScoringMethod.BLENDED

    if disputed:
        status = OutcomeStatus.DISPUTED
    else:
        status = _derive_outcome_status(
            prediction_accuracy=prediction_accuracy,
            support_count=result.support_count,
            contradiction_count=result.contradiction_count,
        )

    outcome = PredictionOutcome(
        id=_build_outcome_id(signal=signal),
        navigation_signal_id=signal.id or "",
        route_prediction_id=result.route_prediction_id,
        evaluation_window_hours=signal.time_horizon_hours,
        prediction_accuracy=prediction_accuracy,
        realized_direction=result.realized_direction,
        realized_magnitude=result.realized_magnitude,
        map_prediction_correct=(not disputed) and prediction_accuracy >= 0.6,
        notes=result.notes_body + _dual_scorer_suffix(
            heuristic_accuracy=result.heuristic_accuracy,
            quant_accuracy=result.quantitative_accuracy,
            disputed=disputed,
        ),
        created_by_agent="score_pending_predictions",
        created_at=scored_at,
        # Phase 12 dual-scorer fields.
        heuristic_accuracy=result.heuristic_accuracy,
        quantitative_accuracy=result.quantitative_accuracy,
        scorer_agreement=scorer_agreement,
        scoring_method=scoring_method,
        consumer_exposure=consumer_exposure,
    )
    return OutcomeDecision(outcome=outcome, status=status)


def _score_flow_family(
    *,
    signal: NavigationSignal,
    route_predictions: Iterable[RoutePrediction],
    stories: list[dict[str, Any]],
    exchange_flows: list[dict[str, Any]],
    stablecoin_activity: list[dict[str, Any]],
) -> FamilyResult:
    """Directional capital-movement scorer (the original v1 rubric).

    Heuristic witness: matching stories / exchange flows / stablecoin activity.
    Quantitative witness: net flow direction from the raw series.
    """
    selected_route = _select_route_prediction(signal=signal, route_predictions=route_predictions)
    predicted_direction = _predicted_direction(signal=signal, route_prediction=selected_route)

    evidence = _collect_evidence(
        signal=signal,
        predicted_direction=predicted_direction,
        stories=stories,
        exchange_flows=exchange_flows,
        stablecoin_activity=stablecoin_activity,
    )

    heuristic_accuracy = _score_accuracy(evidence)
    quant_accuracy = quantitative_score(
        predicted_direction=str(predicted_direction),
        exchange_flows=exchange_flows,
        stablecoin_series=stablecoin_activity,
    ).realized_score
    prediction_accuracy = (heuristic_accuracy + quant_accuracy) / 2.0

    return FamilyResult(
        heuristic_accuracy=heuristic_accuracy,
        quantitative_accuracy=quant_accuracy,
        prediction_accuracy=prediction_accuracy,
        realized_direction=_realized_direction(predicted_direction=predicted_direction, evidence=evidence),
        realized_magnitude=_realized_magnitude(
            signal=signal, evidence=evidence, prediction_accuracy=prediction_accuracy
        ),
        support_count=_support_count(evidence),
        contradiction_count=_contradiction_count(evidence),
        notes_body=_build_flow_notes(
            signal=signal, evidence=evidence, prediction_accuracy=prediction_accuracy
        ),
        route_prediction_id=selected_route.id if selected_route and selected_route.id else None,
    )


def _score_hazard_family(
    *,
    signal: NavigationSignal,
    stories: list[dict[str, Any]],
    exchange_flows: list[dict[str, Any]],
    stablecoin_activity: list[dict[str, Any]],
) -> FamilyResult:
    """route_hazard / route_closure scorer.

    A hazard realizes when danger materializes along the route. The two
    witnesses are independent by construction:

      - Heuristic (stories): danger-flavored stories about the route's asset or
        destination appeared, with no contradicting recovery stories.
      - Quantitative (flow series only): capital actually fled the route — net
        OUTFLOW from the destination, measured by the shared quantitative scorer.
    """
    window_start = _to_utc(signal.created_at)
    window_end = _evaluation_window_end(signal)
    labels = _signal_labels(signal)

    danger_stories: list[dict[str, Any]] = []
    recovery_stories: list[dict[str, Any]] = []
    for story in stories:
        if not _within_window(story, window_start, window_end):
            continue
        if not _matches_any_label(story, labels):
            continue
        text = _record_text(story)
        if _contains_keyword(text, HAZARD_DANGER_KEYWORDS):
            danger_stories.append(story)
        elif _contains_keyword(text, HAZARD_RECOVERY_KEYWORDS):
            recovery_stories.append(story)

    heuristic_accuracy = 0.0
    if danger_stories:
        heuristic_accuracy += HAZARD_WEIGHT_DANGER
    if recovery_stories:
        heuristic_accuracy -= HAZARD_PENALTY_RECOVERY
    else:
        heuristic_accuracy += HAZARD_WEIGHT_NO_RECOVERY
    heuristic_accuracy = _clamp01(heuristic_accuracy)

    # Quantitative witness: a closing/hazardous route should show capital leaving.
    quant_accuracy = quantitative_score(
        predicted_direction=str(FlowDirection.OUTFLOW),
        exchange_flows=exchange_flows,
        stablecoin_series=stablecoin_activity,
    ).realized_score
    prediction_accuracy = (heuristic_accuracy + quant_accuracy) / 2.0

    support_count = 1 if danger_stories else 0
    contradiction_count = 1 if recovery_stories else 0
    if support_count and contradiction_count:
        realized_direction = FlowDirection.MIXED
    elif prediction_accuracy >= 0.6:
        realized_direction = FlowDirection.OUTFLOW
    else:
        realized_direction = FlowDirection.NEUTRAL

    notes_body = (
        f"Hazard evaluation window: {_iso(window_start)} to {_iso(window_end)}. "
        f"Danger stories: {_describe_records(danger_stories)}. "
        f"Recovery stories: {_describe_records(recovery_stories)}. "
        f"Quantitative witness predicted route outflow. "
        f"final_accuracy={prediction_accuracy:.2f}."
    )

    return FamilyResult(
        heuristic_accuracy=heuristic_accuracy,
        quantitative_accuracy=quant_accuracy,
        prediction_accuracy=prediction_accuracy,
        realized_direction=realized_direction,
        realized_magnitude=_magnitude_from_accuracy(signal=signal, prediction_accuracy=prediction_accuracy),
        support_count=support_count,
        contradiction_count=contradiction_count,
        notes_body=notes_body,
    )


def _score_congestion_family(
    *,
    signal: NavigationSignal,
    stories: list[dict[str, Any]],
    exchange_flows: list[dict[str, Any]],
    stablecoin_activity: list[dict[str, Any]],
) -> FamilyResult:
    """congestion_formation scorer.

    Congestion realizes when crowding persists rather than dissipating:

      - Heuristic (stories): activity/crowding stories about the zone appeared,
        with no contradicting dissipation stories.
      - Quantitative (flow series only): sustained on-chain activity referencing
        the zone (record count / elevated magnitude) within the window.
    """
    window_start = _to_utc(signal.created_at)
    window_end = _evaluation_window_end(signal)
    labels = _signal_labels(signal)

    crowding_stories: list[dict[str, Any]] = []
    dissipation_stories: list[dict[str, Any]] = []
    for story in stories:
        if not _within_window(story, window_start, window_end):
            continue
        if not _matches_any_label(story, labels):
            continue
        text = _record_text(story)
        if _contains_keyword(text, CONGESTION_ACTIVITY_KEYWORDS):
            crowding_stories.append(story)
        elif _contains_keyword(text, CONGESTION_DISSIPATE_KEYWORDS):
            dissipation_stories.append(story)

    heuristic_accuracy = 0.0
    if crowding_stories:
        heuristic_accuracy += CONGESTION_WEIGHT_CROWDING
    if dissipation_stories:
        heuristic_accuracy -= CONGESTION_PENALTY_DISSIPATION
    else:
        heuristic_accuracy += CONGESTION_WEIGHT_NO_DISSIPATION
    heuristic_accuracy = _clamp01(heuristic_accuracy)

    # Quantitative witness: did meaningful activity around the zone persist?
    active_records = 0
    for record in (*exchange_flows, *stablecoin_activity):
        if not _within_window(record, window_start, window_end, allow_missing=True):
            continue
        if _matches_any_label(record, labels) or _extract_magnitude(record) in (
            FlowMagnitude.MODERATE,
            FlowMagnitude.HIGH,
        ):
            active_records += 1
    if active_records >= 3:
        quant_accuracy = 0.85
    elif active_records >= 1:
        quant_accuracy = 0.6
    else:
        quant_accuracy = 0.25
    prediction_accuracy = (heuristic_accuracy + quant_accuracy) / 2.0

    support_count = 1 if crowding_stories else 0
    contradiction_count = 1 if dissipation_stories else 0
    realized_direction = (
        FlowDirection.MIXED if (support_count and contradiction_count) else FlowDirection.NEUTRAL
    )

    notes_body = (
        f"Congestion evaluation window: {_iso(window_start)} to {_iso(window_end)}. "
        f"Crowding stories: {_describe_records(crowding_stories)}. "
        f"Dissipation stories: {_describe_records(dissipation_stories)}. "
        f"Active records referencing zone: {active_records}. "
        f"final_accuracy={prediction_accuracy:.2f}."
    )

    return FamilyResult(
        heuristic_accuracy=heuristic_accuracy,
        quantitative_accuracy=quant_accuracy,
        prediction_accuracy=prediction_accuracy,
        realized_direction=realized_direction,
        realized_magnitude=_magnitude_from_accuracy(signal=signal, prediction_accuracy=prediction_accuracy),
        support_count=support_count,
        contradiction_count=contradiction_count,
        notes_body=notes_body,
    )


def run(
    *,
    signal_limit: int = 200,
    context_limit: int = 100,
    dry_run: bool = False,
    now: datetime | None = None,
) -> int:
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
    clickhouse_writer = ClickHouseClient(
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
    pending_signals = _list_pending_signals(clickhouse_reader, limit=signal_limit)
    eligible_signals = [
        signal
        for signal in pending_signals
        if signal.id
        and signal.signal_type in SUPPORTED_SIGNAL_TYPES
        and _evaluation_window_end(signal) <= current_time
    ]
    if not eligible_signals:
        return 0

    existing_outcomes = _list_prediction_outcomes(
        clickhouse_reader,
        navigation_signal_ids=[signal.id or "" for signal in eligible_signals],
    )
    existing_outcomes_by_signal = _latest_outcomes_by_signal(existing_outcomes)
    routes_by_signal = _group_routes_by_signal(
        _list_route_predictions(
            clickhouse_reader,
            navigation_signal_ids=[signal.id or "" for signal in eligible_signals],
        )
    )

    decisions: list[OutcomeDecision] = []
    statuses_to_update: dict[str, OutcomeStatus] = {}

    for signal in eligible_signals:
        signal_id = signal.id or ""
        existing = existing_outcomes_by_signal.get(signal_id)
        if existing is not None:
            statuses_to_update[signal_id] = _status_from_existing_outcome(existing)
            continue

        window_start = _to_utc(signal.created_at)
        window_end = _evaluation_window_end(signal)
        decision = score_prediction(
            signal=signal,
            route_predictions=routes_by_signal.get(signal_id, ()),
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
        decisions.append(decision)
        statuses_to_update[signal_id] = decision.status

    if decisions:
        clickhouse_writer.insert_prediction_outcomes([decision.outcome for decision in decisions])
    if statuses_to_update:
        clickhouse_writer.update_navigation_signal_outcome_statuses(statuses_to_update)
    return len(decisions)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Score pending NavigationSignal predictions.")
    parser.add_argument("--signal-limit", type=int, default=200)
    parser.add_argument("--context-limit", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    inserted = run(
        signal_limit=args.signal_limit,
        context_limit=args.context_limit,
        dry_run=args.dry_run,
    )
    return 0 if inserted >= 0 else 1


def _list_pending_signals(reader: ClickHouseReadClient, *, limit: int) -> list[NavigationSignal]:
    rows = reader.select(
        (
            "SELECT * FROM NavigationSignals "
            "WHERE outcome_status = 'pending' "
            "ORDER BY created_at ASC "
            f"LIMIT {max(0, limit)} FORMAT JSONEachRow"
        )
    )
    return [normalize_navigation_signal_row(row) for row in rows]


def _list_route_predictions(
    reader: ClickHouseReadClient,
    *,
    navigation_signal_ids: Sequence[str],
) -> list[RoutePrediction]:
    if not navigation_signal_ids:
        return []
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


def _collect_evidence(
    *,
    signal: NavigationSignal,
    predicted_direction: FlowDirection,
    stories: Iterable[dict[str, Any]],
    exchange_flows: Iterable[dict[str, Any]],
    stablecoin_activity: Iterable[dict[str, Any]],
) -> EvidenceBucket:
    window_start = _to_utc(signal.created_at)
    window_end = _evaluation_window_end(signal)

    supporting_stories: list[dict[str, Any]] = []
    contradicting_stories: list[dict[str, Any]] = []
    supporting_exchange: list[dict[str, Any]] = []
    contradicting_exchange: list[dict[str, Any]] = []
    supporting_stablecoin: list[dict[str, Any]] = []
    contradicting_stablecoin: list[dict[str, Any]] = []
    skipped_stories = 0
    skipped_exchange = 0
    skipped_stablecoin = 0

    for story in stories:
        timestamp = _extract_timestamp(story)
        if timestamp is None:
            skipped_stories += 1
            continue
        if not (window_start < timestamp <= window_end):
            continue
        relation = _story_relation(signal=signal, story=story)
        if relation > 0:
            supporting_stories.append(story)
        elif relation < 0:
            contradicting_stories.append(story)

    for flow in exchange_flows:
        timestamp = _extract_timestamp(flow)
        if timestamp is None:
            skipped_exchange += 1
            continue
        if not (window_start < timestamp <= window_end):
            continue
        relation = _flow_relation(
            signal=signal,
            item=flow,
            predicted_direction=predicted_direction,
        )
        if relation > 0:
            supporting_exchange.append(flow)
        elif relation < 0:
            contradicting_exchange.append(flow)

    for activity in stablecoin_activity:
        timestamp = _extract_timestamp(activity)
        if timestamp is None:
            skipped_stablecoin += 1
            continue
        if not (window_start < timestamp <= window_end):
            continue
        relation = _stablecoin_relation(
            signal=signal,
            item=activity,
            predicted_direction=predicted_direction,
        )
        if relation > 0:
            supporting_stablecoin.append(activity)
        elif relation < 0:
            contradicting_stablecoin.append(activity)

    return EvidenceBucket(
        supporting_stories=tuple(supporting_stories),
        contradicting_stories=tuple(contradicting_stories),
        supporting_exchange_flows=tuple(supporting_exchange),
        contradicting_exchange_flows=tuple(contradicting_exchange),
        supporting_stablecoin_activity=tuple(supporting_stablecoin),
        contradicting_stablecoin_activity=tuple(contradicting_stablecoin),
        skipped_stories=skipped_stories,
        skipped_exchange_flows=skipped_exchange,
        skipped_stablecoin_activity=skipped_stablecoin,
    )


def _score_accuracy(evidence: EvidenceBucket) -> float:
    score = 0.0
    contradiction_count = 0

    if evidence.supporting_stories:
        score += RUBRIC_WEIGHT_STORIES
    if evidence.supporting_exchange_flows:
        score += RUBRIC_WEIGHT_EXCHANGE
    if evidence.supporting_stablecoin_activity:
        score += RUBRIC_WEIGHT_STABLECOIN

    if evidence.contradicting_stories:
        contradiction_count += 1
    if evidence.contradicting_exchange_flows:
        contradiction_count += 1
    if evidence.contradicting_stablecoin_activity:
        contradiction_count += 1

    score -= contradiction_count * RUBRIC_PENALTY_PER_CONTRADICTION
    if contradiction_count == 0:
        score += RUBRIC_WEIGHT_NO_CONTRADICTION

    return _clamp01(score)


def _realized_direction(
    *,
    predicted_direction: FlowDirection,
    evidence: EvidenceBucket,
) -> FlowDirection:
    support_count = sum(
        1
        for bucket in (
            evidence.supporting_stories,
            evidence.supporting_exchange_flows,
            evidence.supporting_stablecoin_activity,
        )
        if bucket
    )
    contradiction_count = sum(
        1
        for bucket in (
            evidence.contradicting_stories,
            evidence.contradicting_exchange_flows,
            evidence.contradicting_stablecoin_activity,
        )
        if bucket
    )
    if support_count and contradiction_count:
        return FlowDirection.MIXED
    if support_count:
        return predicted_direction
    if contradiction_count:
        return _opposite_direction(predicted_direction)
    return FlowDirection.NEUTRAL


def _realized_magnitude(
    *,
    signal: NavigationSignal,
    evidence: EvidenceBucket,
    prediction_accuracy: float,
) -> FlowMagnitude:
    magnitudes = [
        _extract_magnitude(item)
        for item in (
            *evidence.supporting_stories,
            *evidence.supporting_exchange_flows,
            *evidence.supporting_stablecoin_activity,
        )
    ]
    ranked = [magnitude for magnitude in magnitudes if magnitude is not None]
    if ranked:
        return max(ranked, key=_magnitude_rank)
    if prediction_accuracy >= 0.75 or signal.confidence >= 0.8:
        return FlowMagnitude.HIGH
    if prediction_accuracy >= 0.35:
        return FlowMagnitude.MODERATE
    return FlowMagnitude.LOW


def _support_count(evidence: EvidenceBucket) -> int:
    return sum(
        1
        for bucket in (
            evidence.supporting_stories,
            evidence.supporting_exchange_flows,
            evidence.supporting_stablecoin_activity,
        )
        if bucket
    )


def _contradiction_count(evidence: EvidenceBucket) -> int:
    return sum(
        1
        for bucket in (
            evidence.contradicting_stories,
            evidence.contradicting_exchange_flows,
            evidence.contradicting_stablecoin_activity,
        )
        if bucket
    )


def _derive_outcome_status(
    *,
    prediction_accuracy: float,
    support_count: int,
    contradiction_count: int,
) -> OutcomeStatus:
    # DISPUTED is handled by the caller before this point; this maps a settled
    # (heuristic/quantitative-agreeing) outcome to a status. The logic is
    # family-agnostic: it works from blended accuracy and support/contradiction
    # counts, which every family scorer reports.
    if prediction_accuracy >= 0.6 and contradiction_count == 0:
        return OutcomeStatus.CORRECT
    if support_count and contradiction_count:
        return OutcomeStatus.MIXED
    if 0.0 < prediction_accuracy < 0.6 and support_count:
        return OutcomeStatus.MIXED
    return OutcomeStatus.INCORRECT


def _status_from_existing_outcome(outcome: PredictionOutcome) -> OutcomeStatus:
    if outcome.prediction_accuracy >= 0.6:
        return OutcomeStatus.CORRECT
    if outcome.map_prediction_correct:
        return OutcomeStatus.CORRECT
    if outcome.prediction_accuracy > 0.0:
        return OutcomeStatus.MIXED
    return OutcomeStatus.INCORRECT


def _predicted_direction(
    *,
    signal: NavigationSignal,
    route_prediction: RoutePrediction | None,
) -> FlowDirection:
    if route_prediction is not None:
        return route_prediction.expected_flow_direction
    if signal.destination and signal.destination.lower() == "stablecoins":
        return FlowDirection.OUTFLOW
    return FlowDirection.INFLOW


def _select_route_prediction(
    *,
    signal: NavigationSignal,
    route_predictions: Iterable[RoutePrediction],
) -> RoutePrediction | None:
    ranked = sorted(
        route_predictions,
        key=lambda route: (
            1 if _strings_match(route.origin, signal.origin) else 0,
            1 if _strings_match(route.destination, signal.destination) else 0,
            route.confidence,
            route.created_at,
        ),
        reverse=True,
    )
    return ranked[0] if ranked else None


def _story_relation(*, signal: NavigationSignal, story: dict[str, Any]) -> int:
    story_origin = _string(story.get("origin") or story.get("from"))
    story_destination = _string(story.get("destination") or story.get("to"))
    if story_origin or story_destination:
        if _strings_match(story_origin, signal.origin) and _strings_match(story_destination, signal.destination):
            return 1
        if _strings_match(story_origin, signal.destination) and _strings_match(story_destination, signal.origin):
            return -1

    text = _record_text(story)
    if _text_matches_signal(text=text, origin=signal.origin, destination=signal.destination):
        return 1
    if _text_matches_signal(text=text, origin=signal.destination, destination=signal.origin):
        return -1
    return 0


def _flow_relation(
    *,
    signal: NavigationSignal,
    item: dict[str, Any],
    predicted_direction: FlowDirection,
) -> int:
    direction = _extract_direction(item)
    if direction is None:
        return 0

    destination_match = _item_matches_label(item, signal.destination)
    origin_match = _item_matches_label(item, signal.origin)
    if destination_match:
        if direction == predicted_direction:
            return 1
        if direction == _opposite_direction(predicted_direction):
            return -1
    if origin_match:
        if direction == _opposite_direction(predicted_direction):
            return 1
        if direction == predicted_direction:
            return -1
    return 0


def _stablecoin_relation(
    *,
    signal: NavigationSignal,
    item: dict[str, Any],
    predicted_direction: FlowDirection,
) -> int:
    if not _signal_uses_stablecoins(signal):
        return 0

    direction = _extract_direction(item)
    text = _record_text(item)
    positive_keywords = ("mint", "inflow", "accumulation", "deploy", "deployment", "increase")
    negative_keywords = ("burn", "outflow", "redemption", "distribution", "decrease", "exit")

    if predicted_direction == FlowDirection.INFLOW:
        if direction == FlowDirection.INFLOW or _contains_keyword(text, positive_keywords):
            return 1
        if direction == FlowDirection.OUTFLOW or _contains_keyword(text, negative_keywords):
            return -1
    if predicted_direction == FlowDirection.OUTFLOW:
        if direction == FlowDirection.OUTFLOW or _contains_keyword(text, negative_keywords):
            return 1
        if direction == FlowDirection.INFLOW or _contains_keyword(text, positive_keywords):
            return -1
    return 0


def _dual_scorer_suffix(
    *,
    heuristic_accuracy: float,
    quant_accuracy: float,
    disputed: bool,
) -> str:
    """The family-agnostic dual-scorer tail appended to every outcome's notes."""
    agreement = abs(heuristic_accuracy - quant_accuracy)
    return (
        f" Dual-scorer: heuristic={heuristic_accuracy:.2f}, "
        f"quantitative={quant_accuracy:.2f}, "
        f"agreement_delta={agreement:.2f}"
        f"{', DISPUTED' if disputed else ''}."
    )


def _build_flow_notes(
    *,
    signal: NavigationSignal,
    evidence: EvidenceBucket,
    prediction_accuracy: float,
) -> str:
    window_start = _iso(_to_utc(signal.created_at))
    window_end = _iso(_evaluation_window_end(signal))
    contradiction_count = _contradiction_count(evidence)
    no_contradiction_bonus = RUBRIC_WEIGHT_NO_CONTRADICTION if contradiction_count == 0 else 0.0
    contradiction_penalty = contradiction_count * RUBRIC_PENALTY_PER_CONTRADICTION

    return (
        f"Evaluation window: {window_start} to {window_end}. "
        f"Supporting stories: {_describe_records(evidence.supporting_stories)}. "
        f"Contradicting stories: {_describe_records(evidence.contradicting_stories)}. "
        f"Supporting exchange flows: {_describe_records(evidence.supporting_exchange_flows)}. "
        f"Contradicting exchange flows: {_describe_records(evidence.contradicting_exchange_flows)}. "
        f"Supporting stablecoin activity: {_describe_records(evidence.supporting_stablecoin_activity)}. "
        f"Contradicting stablecoin activity: {_describe_records(evidence.contradicting_stablecoin_activity)}. "
        f"Skipped untimestamped records: stories={evidence.skipped_stories}, "
        f"exchange_flows={evidence.skipped_exchange_flows}, "
        f"stablecoin_activity={evidence.skipped_stablecoin_activity}. "
        f"Rubric totals: stories={RUBRIC_WEIGHT_STORIES if evidence.supporting_stories else 0.0:.1f}, "
        f"exchange={RUBRIC_WEIGHT_EXCHANGE if evidence.supporting_exchange_flows else 0.0:.1f}, "
        f"stablecoins={RUBRIC_WEIGHT_STABLECOIN if evidence.supporting_stablecoin_activity else 0.0:.1f}, "
        f"contradiction_penalty={contradiction_penalty:.1f}, "
        f"no_contradiction_bonus={no_contradiction_bonus:.1f}, "
        f"final_accuracy={prediction_accuracy:.2f}."
    )


def _describe_records(records: Iterable[dict[str, Any]]) -> str:
    parts = []
    for record in records:
        record_id = _string(record.get("id")) or "unknown"
        summary = _string(record.get("summary") or record.get("title") or record.get("story_type")) or "no summary"
        parts.append(f"{record_id} ({summary})")
    return "; ".join(parts) if parts else "none"


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
    route_predictions: Iterable[RoutePrediction],
) -> dict[str, tuple[RoutePrediction, ...]]:
    grouped: dict[str, list[RoutePrediction]] = {}
    for route in route_predictions:
        grouped.setdefault(route.navigation_signal_id, []).append(route)
    return {key: tuple(value) for key, value in grouped.items()}


def _evaluation_window_end(signal: NavigationSignal) -> datetime:
    return _to_utc(signal.created_at) + timedelta(hours=max(0, signal.time_horizon_hours))


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _signal_labels(signal: NavigationSignal) -> tuple[str, ...]:
    """The asset/destination/origin labels a hazard or congestion signal is about."""
    candidates = (signal.destination, signal.origin, *signal.asset_scope)
    return tuple(label for label in candidates if label)


def _matches_any_label(record: dict[str, Any], labels: Sequence[str]) -> bool:
    return any(_item_matches_label(record, label) for label in labels)


def _within_window(
    record: dict[str, Any],
    window_start: datetime,
    window_end: datetime,
    *,
    allow_missing: bool = False,
) -> bool:
    """Whether a record's timestamp falls inside the evaluation window.

    ``allow_missing`` controls untimestamped records: stories are required to be
    timestamped (so future/unknown data cannot leak in), while flow records —
    already window-bounded by the API query — are counted when no timestamp is
    present so a genuinely active window is not under-counted.
    """
    timestamp = _extract_timestamp(record)
    if timestamp is None:
        return allow_missing
    return window_start < timestamp <= window_end


def _magnitude_from_accuracy(
    *,
    signal: NavigationSignal,
    prediction_accuracy: float,
) -> FlowMagnitude:
    if prediction_accuracy >= 0.75 or signal.confidence >= 0.8:
        return FlowMagnitude.HIGH
    if prediction_accuracy >= 0.35:
        return FlowMagnitude.MODERATE
    return FlowMagnitude.LOW


def _build_outcome_id(signal: NavigationSignal) -> str:
    signal_id = signal.id or "signal"
    epoch = int(_evaluation_window_end(signal).timestamp())
    return f"outcome_{signal_id}_{epoch}"


def _signal_uses_stablecoins(signal: NavigationSignal) -> bool:
    return any(
        _strings_match(label, "stablecoins")
        for label in (
            signal.origin,
            signal.destination,
            *signal.asset_scope,
        )
    )


def _extract_timestamp(item: dict[str, Any]) -> datetime | None:
    for key in ("timestamp", "created_at", "observed_at", "window_end", "ended_at", "time"):
        value = item.get(key)
        parsed = _parse_datetime(value)
        if parsed is not None:
            return parsed
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return _to_utc(value)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=UTC)
    text = str(value).strip()
    try:
        if text.endswith("Z"):
            return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
        if "T" in text:
            parsed = datetime.fromisoformat(text)
            return _to_utc(parsed)
        parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        return parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _extract_direction(item: dict[str, Any]) -> FlowDirection | None:
    for key in ("direction", "flow_direction", "net_flow_direction", "realized_direction"):
        raw = _string(item.get(key))
        if raw in {member.value for member in FlowDirection}:
            return FlowDirection(raw)

    text = _record_text(item)
    if any(keyword in text for keyword in ("outflow", "exit", "distribution", "withdraw")):
        return FlowDirection.OUTFLOW
    if any(keyword in text for keyword in ("inflow", "accumulation", "deploy", "mint")):
        return FlowDirection.INFLOW
    return None


def _extract_magnitude(item: dict[str, Any]) -> FlowMagnitude | None:
    for key in ("magnitude", "flow_magnitude", "realized_magnitude", "strength"):
        raw = _string(item.get(key))
        if raw in {member.value for member in FlowMagnitude}:
            return FlowMagnitude(raw)

    text = _record_text(item)
    if any(keyword in text for keyword in ("surge", "spike", "high", "strong")):
        return FlowMagnitude.HIGH
    if any(keyword in text for keyword in ("moderate", "steady")):
        return FlowMagnitude.MODERATE
    if any(keyword in text for keyword in ("low", "weak", "small")):
        return FlowMagnitude.LOW
    return None


def _record_text(item: dict[str, Any]) -> str:
    values = []
    for key in (
        "summary",
        "title",
        "story_type",
        "origin",
        "destination",
        "asset",
        "asset_symbol",
        "protocol",
        "protocol_name",
        "category",
        "sector",
    ):
        value = _string(item.get(key))
        if value:
            values.append(value)
    return " ".join(values).lower()


def _text_matches_signal(*, text: str, origin: str | None, destination: str | None) -> bool:
    if not text:
        return False
    destination_hit = _label_in_text(destination, text)
    origin_hit = _label_in_text(origin, text) if origin else True
    return destination_hit and origin_hit


def _item_matches_label(item: dict[str, Any], label: str | None) -> bool:
    if not label:
        return False
    for key in ("origin", "destination", "asset", "asset_symbol", "protocol", "protocol_name", "category", "sector"):
        if _strings_match(item.get(key), label):
            return True
    return _label_in_text(label, _record_text(item))


def _label_in_text(label: str | None, text: str) -> bool:
    normalized_label = _normalize_text(label)
    if not normalized_label:
        return False
    return normalized_label in _normalize_text(text)


def _strings_match(left: Any, right: Any) -> bool:
    return bool(_normalize_text(left) and _normalize_text(left) == _normalize_text(right))


def _normalize_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    raw = str(value).replace("_", " ").replace("-", " ").lower()
    filtered = "".join(character if character.isalnum() or character.isspace() else " " for character in raw)
    return " ".join(filtered.split())


def _contains_keyword(text: str, keywords: Sequence[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _opposite_direction(direction: FlowDirection) -> FlowDirection:
    if direction is FlowDirection.INFLOW:
        return FlowDirection.OUTFLOW
    if direction is FlowDirection.OUTFLOW:
        return FlowDirection.INFLOW
    return FlowDirection.MIXED


def _magnitude_rank(magnitude: FlowMagnitude) -> int:
    if magnitude is FlowMagnitude.HIGH:
        return 3
    if magnitude is FlowMagnitude.MODERATE:
        return 2
    return 1


def _sql_string_list(values: Sequence[str]) -> str:
    return ",".join(_sql_string(value) for value in values if value)


def _sql_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _utcnow() -> datetime:
    return datetime.now(UTC)


if __name__ == "__main__":
    raise SystemExit(main())
