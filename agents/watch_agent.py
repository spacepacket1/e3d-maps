from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Mapping

from agents.base_agent import AgentError, BaseAgent
from clients.qwen_client import QwenClient, QwenClientError
from schemas.shared_enums import (
    FlowDirection,
    FlowMagnitude,
    is_known_signal_type,
)
from schemas.watch_prediction import WatchPrediction

WATCH_SCHEMA_VERSION = "watch_v1"


@dataclass(frozen=True)
class WatchPredictionResult:
    prediction: WatchPrediction | None
    raw_response: str | None = None
    parsed_output: Any = None
    used_fallback: bool = False
    fallback_reason: str | None = None
    skipped_reason: str | None = None


class WatchAgent(BaseAgent):
    """Consumes one notable signal (from the public Maps contract) and emits a
    falsifiable WatchPrediction.

    The model supplies only the claim + expected direction/magnitude/window; the
    numeric ``probability`` is derived deterministically here, never read from
    the model. A model failure degrades to a deterministic fallback prediction
    so a scheduler tick never crashes.
    """

    def __init__(
        self,
        *,
        qwen_client: QwenClient,
        model_name: str | None = None,
        adapter_name: str = "base-v0",
        adapter_path: str | None = None,
    ) -> None:
        super().__init__(
            agent_name="watch_agent",
            question_template=(
                "Given this notable signal, what is the single most falsifiable "
                "flow prediction for the next {time_horizon_hours} hours?"
            ),
            system_prompt=self.load_prompt("prompts/maps_system_prompt.md"),
            agent_prompt=self.load_prompt("prompts/watch_agent.md"),
            qwen_client=qwen_client,
            model_name=model_name,
            adapter_name=adapter_name,
            adapter_path=adapter_path,
        )

    def predict(
        self,
        signal: Mapping[str, Any],
        *,
        now: datetime | None = None,
    ) -> WatchPredictionResult:
        created_at = now or datetime.now(UTC)
        source_signal_id = str(signal.get("signal_id") or signal.get("source_signal_id") or "")
        signal_type = str(signal.get("signal_type") or "")

        if not source_signal_id:
            return WatchPredictionResult(prediction=None, skipped_reason="missing source signal id")
        if not is_known_signal_type(signal_type):
            return WatchPredictionResult(
                prediction=None,
                skipped_reason=f"unknown signal_type {signal_type!r}",
            )

        prompt = self.build_prompt(self._build_signal_context(signal))

        raw_response: str | None = None
        parsed_output: Any = None
        try:
            raw_response = self.call_qwen(prompt)
            if not raw_response or not raw_response.strip():
                raise AgentError("empty model output")
            parsed_output = self.parse_json(raw_response)
            claim, direction, magnitude, window = self._validate_model_output(parsed_output)
            prediction = self._build_prediction(
                signal=signal,
                source_signal_id=source_signal_id,
                signal_type=signal_type,
                claim=claim,
                direction=direction,
                magnitude=magnitude,
                window=window,
                created_at=created_at,
            )
            return WatchPredictionResult(
                prediction=prediction,
                raw_response=raw_response,
                parsed_output=parsed_output,
                used_fallback=False,
            )
        except (AgentError, QwenClientError, ValueError) as exc:
            fallback = self._build_fallback(
                signal=signal,
                source_signal_id=source_signal_id,
                signal_type=signal_type,
                created_at=created_at,
            )
            return WatchPredictionResult(
                prediction=fallback,
                raw_response=raw_response,
                parsed_output=parsed_output,
                used_fallback=True,
                fallback_reason=str(exc),
            )

    # ── prompt context ────────────────────────────────────────────────────────

    def _build_signal_context(self, signal: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "question": self.question_template.format(time_horizon_hours=24),
            "signal": {
                "signal_id": signal.get("signal_id") or signal.get("source_signal_id"),
                "signal_type": signal.get("signal_type"),
                "asset_scope": list(signal.get("asset_scope") or []),
                "chain_scope": list(signal.get("chain_scope") or []),
                "origin": signal.get("origin"),
                "destination": signal.get("destination"),
                "confidence": signal.get("confidence"),
                "notability": signal.get("notability"),
                "summary": signal.get("summary"),
            },
        }

    # ── validation of model output (local, not NavigationSignal-shaped) ────────

    @staticmethod
    def _validate_model_output(
        parsed_output: Any,
    ) -> tuple[str, FlowDirection, FlowMagnitude, int]:
        if not isinstance(parsed_output, Mapping):
            raise ValueError("watch agent output must be a JSON object")

        claim = parsed_output.get("claim")
        if not isinstance(claim, str) or not claim.strip():
            raise ValueError("claim must be a non-empty string")

        try:
            direction = FlowDirection(str(parsed_output.get("realized_direction_expected")))
        except ValueError as exc:
            raise ValueError("realized_direction_expected is not a valid FlowDirection") from exc
        try:
            magnitude = FlowMagnitude(str(parsed_output.get("magnitude_expected")))
        except ValueError as exc:
            raise ValueError("magnitude_expected is not a valid FlowMagnitude") from exc

        window_raw = parsed_output.get("evaluation_window_hours")
        try:
            window = int(window_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("evaluation_window_hours must be an integer") from exc
        if window <= 0:
            raise ValueError("evaluation_window_hours must be positive")

        return claim.strip(), direction, magnitude, window

    # ── prediction assembly ────────────────────────────────────────────────────

    def _build_prediction(
        self,
        *,
        signal: Mapping[str, Any],
        source_signal_id: str,
        signal_type: str,
        claim: str,
        direction: FlowDirection,
        magnitude: FlowMagnitude,
        window: int,
        created_at: datetime,
    ) -> WatchPrediction:
        probability = self._derive_probability(
            source_confidence=_as_float(signal.get("confidence")),
            utility=_source_utility(signal),
        )
        idempotency_key = self._idempotency_key(
            source_signal_id=source_signal_id,
            window=window,
            magnitude=magnitude,
            direction=direction,
        )
        return WatchPrediction(
            id=f"watchpred_{idempotency_key[:12]}",
            source_signal_id=source_signal_id,
            source_prediction_id=signal.get("source_prediction_id") or None,
            signal_type=signal_type,
            asset_scope=list(signal.get("asset_scope") or []),
            chain_scope=list(signal.get("chain_scope") or []),
            claim=claim,
            probability=probability,
            realized_direction_expected=direction,
            magnitude_expected=magnitude,
            evaluation_window_hours=window,
            created_by_agent=self.agent_name,
            model=self.model_name,
            adapter=self.adapter_name,
            schema_version=WATCH_SCHEMA_VERSION,
            idempotency_key=idempotency_key,
            created_at=created_at,
        )

    def _build_fallback(
        self,
        *,
        signal: Mapping[str, Any],
        source_signal_id: str,
        signal_type: str,
        created_at: datetime,
    ) -> WatchPrediction:
        confidence = _as_float(signal.get("confidence"))
        direction = _infer_direction(signal)
        magnitude = _magnitude_from_confidence(confidence)
        window = 24
        claim = _fallback_claim(
            signal=signal,
            signal_type=signal_type,
            direction=direction,
            magnitude=magnitude,
            window=window,
        )
        return self._build_prediction(
            signal=signal,
            source_signal_id=source_signal_id,
            signal_type=signal_type,
            claim=claim,
            direction=direction,
            magnitude=magnitude,
            window=window,
            created_at=created_at,
        )

    # ── deterministic derivations ──────────────────────────────────────────────

    @staticmethod
    def _derive_probability(*, source_confidence: float, utility: float | None) -> float:
        confidence = _clamp01(source_confidence)
        if utility is None:
            return confidence
        u = _clamp01(utility)
        return _clamp01(confidence * (0.5 + 0.5 * u))

    @staticmethod
    def _idempotency_key(
        *,
        source_signal_id: str,
        window: int,
        magnitude: FlowMagnitude,
        direction: FlowDirection,
    ) -> str:
        raw = f"{source_signal_id}|{window}|{magnitude.value}|{direction.value}"
        return sha256(raw.encode("utf-8")).hexdigest()


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _source_utility(signal: Mapping[str, Any]) -> float | None:
    """Return the source signal's utility if the public payload carries it.

    The public notable contract exposes ``notability`` (for ranking) and
    ``confidence`` only, not the raw utility score, so over the public contract
    this is typically None and probability falls back to confidence. Tests and
    enriched callers may supply ``final_signal_utility_score`` / ``utility``.
    """
    for key in ("final_signal_utility_score", "utility"):
        if key in signal and signal[key] is not None:
            return _as_float(signal[key])
    return None


def _magnitude_from_confidence(confidence: float) -> FlowMagnitude:
    if confidence >= 0.75:
        return FlowMagnitude.HIGH
    if confidence >= 0.5:
        return FlowMagnitude.MODERATE
    return FlowMagnitude.LOW


_INFLOW_TOKENS = ("inflow", "into", "accumulat", "buy", "bid")
_OUTFLOW_TOKENS = ("outflow", "out of", "exit", "distribut", "sell", "withdraw")


def _infer_direction(signal: Mapping[str, Any]) -> FlowDirection:
    text = str(signal.get("summary") or "").lower()
    has_in = any(token in text for token in _INFLOW_TOKENS)
    has_out = any(token in text for token in _OUTFLOW_TOKENS)
    if has_in and has_out:
        return FlowDirection.MIXED
    if has_in:
        return FlowDirection.INFLOW
    if has_out:
        return FlowDirection.OUTFLOW
    return FlowDirection.NEUTRAL


def _fallback_claim(
    *,
    signal: Mapping[str, Any],
    signal_type: str,
    direction: FlowDirection,
    magnitude: FlowMagnitude,
    window: int,
) -> str:
    assets = ", ".join(str(a) for a in (signal.get("asset_scope") or []) if a)
    chains = ", ".join(str(c) for c in (signal.get("chain_scope") or []) if c)
    scope_bits = []
    if assets:
        scope_bits.append(assets)
    if chains:
        scope_bits.append(f"on {chains}")
    scope = (" for " + " ".join(scope_bits)) if scope_bits else ""
    readable_type = signal_type.replace("_", " ")
    return (
        f"Following the {readable_type} signal{scope}, expect {direction.value} flow "
        f"of {magnitude.value} magnitude within {window} hours."
    )
