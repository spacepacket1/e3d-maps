from __future__ import annotations

import argparse
import json
from base64 import b64encode
from dataclasses import dataclass
from datetime import UTC, datetime
from math import tanh
from typing import Any, Iterable, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from api.normalizers import (
    normalize_cross_chain_activity_state_row,
    normalize_maps_news_brief_row,
    normalize_navigation_signal_row,
    normalize_route_prediction_row,
    normalize_traffic_state_row,
)
from schemas.cross_chain_activity_state import CrossChainActivityState
from schemas.maps_news_brief import MapsNewsBrief
from clients.clickhouse_client import ClickHouseClient
from clients.trading_outcome_client import TradingOutcomeClient
from schemas.navigation_signal import NavigationSignal
from schemas.route_prediction import RoutePrediction
from schemas.shared_enums import OutcomeStatus
from schemas.signal_utility_score import SignalUtilityScore
from schemas.traffic_state import TrafficState
from settings import MapsRunnerSettings


@dataclass(frozen=True)
class SignalFeedbackBundle:
    actions: tuple[dict[str, Any], ...]
    outcomes: tuple[dict[str, Any], ...]
    verdicts: tuple[dict[str, Any], ...]


class ClickHouseReadClientError(RuntimeError):
    """Raised when a ClickHouse read query fails."""


class ClickHouseReadClient:
    def __init__(
        self,
        *,
        host: str = "localhost",
        port: int = 8123,
        database: str = "default",
        username: str = "default",
        password: str = "",
        secure: bool = False,
        timeout: float = 10.0,
        request_executor=None,
    ) -> None:
        self.host = host
        self.port = port
        self.database = database
        self.username = username
        self.password = password
        self.secure = secure
        self.timeout = timeout
        self._request_executor = request_executor or self._default_request_executor

    def list_navigation_signals(self, *, limit: int = 200) -> list[NavigationSignal]:
        rows = self.select(
            (
                "SELECT * FROM NavigationSignals "
                "ORDER BY created_at DESC "
                f"LIMIT {max(0, limit)} FORMAT JSONEachRow"
            )
        )
        return [normalize_navigation_signal_row(row) for row in rows]

    def list_route_predictions(self, *, limit: int = 500) -> list[RoutePrediction]:
        rows = self.select(
            (
                "SELECT * FROM RoutePredictions "
                "ORDER BY created_at DESC "
                f"LIMIT {max(0, limit)} FORMAT JSONEachRow"
            )
        )
        return [normalize_route_prediction_row(row) for row in rows]

    def get_latest_traffic_state(self) -> TrafficState | None:
        rows = self.select(
            "SELECT * FROM TrafficStates ORDER BY created_at DESC, id DESC LIMIT 1 FORMAT JSONEachRow"
        )
        if not rows:
            return None
        return normalize_traffic_state_row(rows[0])

    def get_latest_cross_chain_activity_state(self) -> CrossChainActivityState | None:
        rows = self.select(
            "SELECT * FROM CrossChainActivityStates ORDER BY created_at DESC, id DESC LIMIT 1 FORMAT JSONEachRow"
        )
        if not rows:
            return None
        return normalize_cross_chain_activity_state_row(rows[0])

    def get_latest_maps_news_brief(self) -> MapsNewsBrief | None:
        rows = self.select(
            "SELECT * FROM MapsNewsBriefs ORDER BY created_at DESC, id DESC LIMIT 1 FORMAT JSONEachRow"
        )
        if not rows:
            return None
        return normalize_maps_news_brief_row(rows[0])

    def select(self, query: str) -> list[dict[str, Any]]:
        request = self._build_request(query)
        try:
            raw = self._request_executor(request, self.timeout)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ClickHouseReadClientError(
                f"ClickHouse query failed with status {exc.code}: {detail}"
            ) from exc
        except URLError as exc:
            raise ClickHouseReadClientError(f"ClickHouse query failed: {exc.reason}") from exc

        if not raw:
            return []

        rows: list[dict[str, Any]] = []
        for line in raw.decode("utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if isinstance(payload, dict):
                rows.append(payload)
        return rows

    def _build_request(self, query: str) -> Request:
        scheme = "https" if self.secure else "http"
        url = f"{scheme}://{self.host}:{self.port}/?database={self.database}"
        headers = {"Content-Type": "text/plain; charset=utf-8"}
        if self.username or self.password:
            token = b64encode(f"{self.username}:{self.password}".encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {token}"
        return Request(url=url, data=query.encode("utf-8"), headers=headers, method="POST")

    @staticmethod
    def _default_request_executor(request: Request, timeout: float) -> bytes:
        with urlopen(request, timeout=timeout) as response:
            return response.read()


def compute_signal_utility_scores(
    *,
    navigation_signals: Iterable[NavigationSignal],
    route_predictions: Iterable[RoutePrediction],
    trading_actions: Iterable[dict[str, Any]],
    trading_outcomes: Iterable[dict[str, Any]],
    trading_verdicts: Iterable[dict[str, Any]],
    created_at: datetime | None = None,
) -> list[SignalUtilityScore]:
    timestamp = _utcnow() if created_at is None else _to_utc(created_at)
    actions = tuple(trading_actions)
    outcomes = tuple(trading_outcomes)
    verdicts = tuple(trading_verdicts)
    routes_by_signal = _group_routes_by_signal(route_predictions)
    scores: list[SignalUtilityScore] = []

    for signal in navigation_signals:
        feedback = _collect_feedback(
            signal=signal,
            route_predictions=routes_by_signal.get(signal.id or "", ()),
            trading_actions=actions,
            trading_outcomes=outcomes,
            trading_verdicts=verdicts,
        )
        if not feedback.actions and not feedback.outcomes and not feedback.verdicts:
            continue

        linked_action_ids = _ordered_ids(feedback.actions)
        linked_outcome_ids = _ordered_ids(feedback.outcomes)
        sample_size = _sample_size(feedback)
        if sample_size == 0:
            continue

        prediction_accuracy = _prediction_accuracy(signal=signal, feedback=feedback)
        economic_utility = _economic_utility(feedback)
        risk_reduction_utility = _risk_reduction_utility(feedback)
        confidence_calibration_error = _clamp01(abs(signal.confidence - prediction_accuracy))
        execution_quality = _execution_quality(feedback)
        execution_adjusted_utility = _execution_adjusted_utility(
            prediction_accuracy=prediction_accuracy,
            economic_utility=economic_utility,
            execution_quality=execution_quality,
        )
        final_signal_utility_score = _final_signal_utility_score(
            prediction_accuracy=prediction_accuracy,
            economic_utility=economic_utility,
            risk_reduction_utility=risk_reduction_utility,
            confidence_calibration_error=confidence_calibration_error,
            execution_adjusted_utility=execution_adjusted_utility,
        )

        scores.append(
            SignalUtilityScore(
                id=None,
                navigation_signal_id=signal.id or "",
                sample_size=sample_size,
                prediction_accuracy=prediction_accuracy,
                economic_utility=economic_utility,
                risk_reduction_utility=risk_reduction_utility,
                confidence_calibration_error=confidence_calibration_error,
                execution_adjusted_utility=execution_adjusted_utility,
                final_signal_utility_score=final_signal_utility_score,
                linked_action_ids=linked_action_ids,
                linked_outcome_ids=linked_outcome_ids,
                created_at=timestamp,
            )
        )

    return scores


def run(
    *,
    signal_limit: int = 200,
    route_limit: int = 500,
    feedback_limit: int = 500,
    dry_run: bool = False,
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
    trading_client = TradingOutcomeClient(
        base_url=settings.e3d_base_url,
        api_prefix=settings.e3d_api_prefix,
        api_key=settings.e3d_api_key,
        timeout=settings.clickhouse_timeout,
    )

    scores = compute_signal_utility_scores(
        navigation_signals=clickhouse_reader.list_navigation_signals(limit=signal_limit),
        route_predictions=clickhouse_reader.list_route_predictions(limit=route_limit),
        trading_actions=trading_client.get_recent_actions(max_items=feedback_limit),
        trading_outcomes=trading_client.get_recent_outcomes(max_items=feedback_limit),
        trading_verdicts=trading_client.get_recent_verdicts(max_items=feedback_limit),
    )
    if not scores:
        return 0
    return clickhouse_writer.insert_signal_utility_scores(scores)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compute SignalUtilityScore rows from trading feedback.")
    parser.add_argument("--signal-limit", type=int, default=200)
    parser.add_argument("--route-limit", type=int, default=500)
    parser.add_argument("--feedback-limit", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    inserted = run(
        signal_limit=args.signal_limit,
        route_limit=args.route_limit,
        feedback_limit=args.feedback_limit,
        dry_run=args.dry_run,
    )
    return 0 if inserted >= 0 else 1


def _collect_feedback(
    *,
    signal: NavigationSignal,
    route_predictions: Iterable[RoutePrediction],
    trading_actions: Iterable[dict[str, Any]],
    trading_outcomes: Iterable[dict[str, Any]],
    trading_verdicts: Iterable[dict[str, Any]],
) -> SignalFeedbackBundle:
    signal_id = signal.id or ""
    route_ids = {route.id for route in route_predictions if route.id}
    linked_actions = tuple(
        action for action in trading_actions if _record_links_signal(action, signal_id, route_ids)
    )
    action_ids = {record_id for record_id in _ordered_ids(linked_actions)}
    linked_outcomes = tuple(
        outcome
        for outcome in trading_outcomes
        if _record_links_signal(outcome, signal_id, route_ids)
        or _record_links_action(outcome, action_ids)
        or _record_id(outcome) in set(signal.supporting_outcome_ids)
    )
    outcome_ids = {record_id for record_id in _ordered_ids(linked_outcomes)}
    linked_verdicts = tuple(
        verdict
        for verdict in trading_verdicts
        if _record_links_signal(verdict, signal_id, route_ids)
        or _record_links_action(verdict, action_ids)
        or _record_links_outcome(verdict, outcome_ids)
    )
    return SignalFeedbackBundle(
        actions=linked_actions,
        outcomes=linked_outcomes,
        verdicts=linked_verdicts,
    )


def _group_routes_by_signal(
    route_predictions: Iterable[RoutePrediction],
) -> dict[str, tuple[RoutePrediction, ...]]:
    grouped: dict[str, list[RoutePrediction]] = {}
    for route in route_predictions:
        grouped.setdefault(route.navigation_signal_id, []).append(route)
    return {key: tuple(value) for key, value in grouped.items()}


def _record_links_signal(record: dict[str, Any], signal_id: str, route_ids: set[str]) -> bool:
    if not signal_id:
        return False
    if signal_id in _string_set(record.get("navigation_signal_ids")):
        return True
    if _string(record.get("navigation_signal_id")) == signal_id:
        return True
    return bool(route_ids.intersection(_string_set(record.get("route_prediction_ids"))))


def _record_links_action(record: dict[str, Any], action_ids: set[str]) -> bool:
    if not action_ids:
        return False
    if _string(record.get("action_id")) in action_ids:
        return True
    if _string(record.get("trading_action_id")) in action_ids:
        return True
    linked_action_ids = _string_set(record.get("action_ids")) | _string_set(record.get("trading_action_ids"))
    return bool(action_ids.intersection(linked_action_ids))


def _record_links_outcome(record: dict[str, Any], outcome_ids: set[str]) -> bool:
    if not outcome_ids:
        return False
    if _string(record.get("outcome_id")) in outcome_ids:
        return True
    linked_outcome_ids = _string_set(record.get("outcome_ids")) | _string_set(record.get("trading_outcome_ids"))
    return bool(outcome_ids.intersection(linked_outcome_ids))


def _ordered_ids(records: Iterable[dict[str, Any]]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for record in records:
        record_id = _record_id(record)
        if not record_id or record_id in seen:
            continue
        seen.add(record_id)
        ordered.append(record_id)
    return ordered


def _sample_size(feedback: SignalFeedbackBundle) -> int:
    identified_ids = set(_ordered_ids(feedback.actions))
    identified_ids.update(_ordered_ids(feedback.outcomes))
    identified_ids.update(_ordered_ids(feedback.verdicts))
    anonymous_count = sum(
        1
        for record in (*feedback.actions, *feedback.outcomes, *feedback.verdicts)
        if _record_id(record) is None
    )
    return len(identified_ids) + anonymous_count


def _prediction_accuracy(*, signal: NavigationSignal, feedback: SignalFeedbackBundle) -> float:
    values = _extract_numeric_scores(
        (*feedback.outcomes, *feedback.verdicts),
        direct_keys=("prediction_accuracy", "map_prediction_accuracy"),
        boolean_keys=("map_prediction_correct", "signal_correct", "thesis_correct"),
    )
    if values:
        return _average(values)

    status_score = _outcome_status_score(signal.outcome_status)
    if status_score is not None:
        return status_score
    return 0.5


def _economic_utility(feedback: SignalFeedbackBundle) -> float:
    explicit = _extract_numeric_scores(
        (*feedback.outcomes, *feedback.verdicts),
        direct_keys=("economic_utility", "economic_utility_score", "utility_score"),
        boolean_keys=(),
    )
    if explicit:
        return _average(explicit)

    derived = [
        score
        for score in (_derive_economic_utility(outcome) for outcome in feedback.outcomes)
        if score is not None
    ]
    if derived:
        return _average(derived)
    return 0.5


def _risk_reduction_utility(feedback: SignalFeedbackBundle) -> float:
    explicit = _extract_numeric_scores(
        (*feedback.outcomes, *feedback.verdicts),
        direct_keys=("risk_reduction_utility", "risk_reduction_score"),
        boolean_keys=("risk_management_correct", "reduced_risk", "drawdown_contained"),
    )
    if explicit:
        return _average(explicit)

    drawdown_scores = [
        score
        for score in (_derive_drawdown_score(outcome) for outcome in feedback.outcomes)
        if score is not None
    ]
    if drawdown_scores:
        return _average(drawdown_scores)
    return 0.5


def _execution_quality(feedback: SignalFeedbackBundle) -> float:
    explicit = _extract_numeric_scores(
        (*feedback.outcomes, *feedback.verdicts),
        direct_keys=("execution_quality", "execution_quality_score", "trade_execution_score"),
        boolean_keys=("trade_execution_correct", "timing_correct", "entry_correct"),
    )
    if explicit:
        return _average(explicit)
    return 0.5


def _execution_adjusted_utility(
    *,
    prediction_accuracy: float,
    economic_utility: float,
    execution_quality: float,
) -> float:
    return _clamp01((prediction_accuracy * 0.65) + (economic_utility * execution_quality * 0.35))


def _final_signal_utility_score(
    *,
    prediction_accuracy: float,
    economic_utility: float,
    risk_reduction_utility: float,
    confidence_calibration_error: float,
    execution_adjusted_utility: float,
) -> float:
    calibration_utility = 1.0 - confidence_calibration_error
    return _clamp01(
        (prediction_accuracy * 0.35)
        + (execution_adjusted_utility * 0.25)
        + (risk_reduction_utility * 0.20)
        + (economic_utility * 0.10)
        + (calibration_utility * 0.10)
    )


def _extract_numeric_scores(
    records: Iterable[dict[str, Any]],
    *,
    direct_keys: Sequence[str],
    boolean_keys: Sequence[str],
) -> list[float]:
    scores: list[float] = []
    for record in records:
        for key in direct_keys:
            value = _float_or_none(record.get(key))
            if value is not None:
                scores.append(_clamp01(value))
                break
        else:
            for key in boolean_keys:
                boolean_value = _bool_or_none(record.get(key))
                if boolean_value is not None:
                    scores.append(1.0 if boolean_value else 0.0)
                    break
    return scores


def _derive_economic_utility(outcome: dict[str, Any]) -> float | None:
    return_pct = _float_or_none(
        outcome.get("return_pct")
        or outcome.get("pnl_pct")
        or outcome.get("profit_pct")
        or outcome.get("roi_pct")
    )
    if return_pct is not None:
        return _squash_percent(return_pct)

    pnl = _float_or_none(
        outcome.get("pnl_usd")
        or outcome.get("realized_pnl_usd")
        or outcome.get("profit_usd")
        or outcome.get("loss_usd")
    )
    if pnl is None:
        return None

    notional = _float_or_none(
        outcome.get("position_notional_usd")
        or outcome.get("trade_notional_usd")
        or outcome.get("entry_notional_usd")
        or outcome.get("risk_budget_usd")
    )
    if notional is None or notional == 0:
        return _clamp01(0.5 + (0.25 if pnl > 0 else -0.25 if pnl < 0 else 0.0))

    normalized_return_pct = (pnl / abs(notional)) * 100.0
    return _squash_percent(normalized_return_pct)


def _derive_drawdown_score(outcome: dict[str, Any]) -> float | None:
    max_drawdown_pct = _float_or_none(
        outcome.get("max_drawdown_pct") or outcome.get("drawdown_pct") or outcome.get("adverse_excursion_pct")
    )
    if max_drawdown_pct is None:
        return None
    return _clamp01(1.0 - min(abs(max_drawdown_pct), 100.0) / 100.0)


def _squash_percent(value: float) -> float:
    return _clamp01(0.5 + (0.5 * tanh(value / 20.0)))


def _outcome_status_score(status: OutcomeStatus) -> float | None:
    if status is OutcomeStatus.CORRECT:
        return 1.0
    if status is OutcomeStatus.MIXED:
        return 0.5
    if status is OutcomeStatus.INCORRECT:
        return 0.0
    return None


def _average(values: Sequence[float]) -> float:
    if not values:
        return 0.5
    return _clamp01(sum(values) / len(values))


def _record_id(record: dict[str, Any]) -> str | None:
    return _string(record.get("id"))


def _string_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item) for item in value if str(item)}


def _string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value)
    return text or None


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return None


def split_accuracy_by_exposure(
    prediction_accuracy: float,
    consumer_exposure: int,
) -> tuple[float | None, float | None]:
    """Split a settled accuracy into (exogenous_accuracy, induced_accuracy).

    Reflexivity model: an outcome is *exogenous* when no downstream consumer
    acted on the signal before its window closed (``consumer_exposure == 0``),
    and *induced* when at least one did. The split is recorded per row so the
    two populations stay queryable via ``avg(exogenous_accuracy)`` /
    ``avg(induced_accuracy)``. Returns ``(None, None)`` shapes where the row does
    not belong to that population.
    """
    accuracy = _clamp01(float(prediction_accuracy))
    if consumer_exposure > 0:
        return None, accuracy
    return accuracy, None


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
