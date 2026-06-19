from __future__ import annotations

import json
from datetime import UTC, datetime

from agents.watch_agent import WATCH_SCHEMA_VERSION, WatchAgent, _clamp01
from clients.qwen_client import QwenClient
from schemas.shared_enums import FlowDirection, FlowMagnitude


class StubQwenClient(QwenClient):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(request_executor=lambda request, timeout: b"")
        self._responses = list(responses)

    def generate(self, **kwargs) -> str:
        return self._responses.pop(0)


class FailingQwenClient(QwenClient):
    def __init__(self) -> None:
        super().__init__(request_executor=lambda request, timeout: b"")

    def generate(self, **kwargs) -> str:
        from clients.qwen_client import QwenClientError

        raise QwenClientError("model down")


def _notable_signal(**overrides):
    signal = {
        "signal_id": "navsig_01J",
        "signal_type": "capital_migration",
        "asset_scope": ["ETH"],
        "chain_scope": ["ethereum"],
        "confidence": 0.8,
        "notability": 80,
        "summary": "ETH is rotating into Coinbase, building sell-side liquidity.",
    }
    signal.update(overrides)
    return signal


VALID_MODEL_JSON = json.dumps(
    {
        "claim": "ETH continues to flow into Coinbase, pressuring price over 24 hours.",
        "realized_direction_expected": "inflow",
        "magnitude_expected": "high",
        "evaluation_window_hours": 24,
    }
)

NOW = datetime(2026, 6, 8, 0, 0, tzinfo=UTC)


def test_valid_model_output_produces_validated_prediction():
    agent = WatchAgent(qwen_client=StubQwenClient([VALID_MODEL_JSON]), model_name="gpt-4o")

    result = agent.predict(_notable_signal(), now=NOW)

    assert result.used_fallback is False
    pred = result.prediction
    assert pred is not None
    assert pred.claim.startswith("ETH continues to flow into Coinbase")
    assert pred.realized_direction_expected == FlowDirection.INFLOW
    assert pred.magnitude_expected == FlowMagnitude.HIGH
    assert pred.evaluation_window_hours == 24
    assert pred.source_signal_id == "navsig_01J"
    assert pred.model == "gpt-4o"
    assert pred.schema_version == WATCH_SCHEMA_VERSION
    assert pred.created_by_agent == "watch_agent"


def test_probability_is_confidence_when_no_utility_available():
    agent = WatchAgent(qwen_client=StubQwenClient([VALID_MODEL_JSON]))

    result = agent.predict(_notable_signal(confidence=0.8), now=NOW)

    # No utility over the public contract -> probability == source confidence.
    assert result.prediction.probability == 0.8


def test_probability_weighted_by_utility_when_available():
    agent = WatchAgent(qwen_client=StubQwenClient([VALID_MODEL_JSON]))

    result = agent.predict(
        _notable_signal(confidence=0.8, final_signal_utility_score=0.5),
        now=NOW,
    )

    # 0.8 * (0.5 + 0.5*0.5) = 0.8 * 0.75 = 0.6
    assert abs(result.prediction.probability - 0.6) < 1e-9


def test_probability_is_clamped_to_unit_interval():
    agent = WatchAgent(qwen_client=StubQwenClient([VALID_MODEL_JSON]))

    result = agent.predict(
        _notable_signal(confidence=5.0, final_signal_utility_score=9.0),
        now=NOW,
    )

    assert result.prediction.probability == 1.0
    assert _clamp01(-3.0) == 0.0


def test_idempotency_key_is_deterministic_and_components_sensitive():
    agent = WatchAgent(qwen_client=StubQwenClient([VALID_MODEL_JSON, VALID_MODEL_JSON]))

    first = agent.predict(_notable_signal(), now=NOW).prediction
    second = agent.predict(_notable_signal(), now=NOW).prediction

    assert first.idempotency_key == second.idempotency_key
    assert first.id == second.id

    # Recompute by hand to confirm the formula.
    from hashlib import sha256

    expected = sha256(b"navsig_01J|24|high|inflow").hexdigest()
    assert first.idempotency_key == expected


def test_invalid_json_falls_back_to_deterministic_prediction():
    agent = WatchAgent(qwen_client=StubQwenClient(["this is not json"]))

    result = agent.predict(_notable_signal(), now=NOW)

    assert result.used_fallback is True
    assert result.fallback_reason is not None
    pred = result.prediction
    assert pred is not None
    # Summary mentions both "into" (inflow) and "sell"-side (outflow) -> the
    # crude fallback heuristic honestly reports MIXED. Magnitude from the 0.8
    # confidence band -> high.
    assert pred.realized_direction_expected == FlowDirection.MIXED
    assert pred.magnitude_expected == FlowMagnitude.HIGH
    assert pred.probability == 0.8
    assert "capital migration" in pred.claim


def test_fallback_infers_inflow_from_unambiguous_summary():
    agent = WatchAgent(qwen_client=StubQwenClient(["not json"]))

    result = agent.predict(
        _notable_signal(summary="Capital is accumulating into ETH DeFi protocols."),
        now=NOW,
    )

    assert result.used_fallback is True
    assert result.prediction.realized_direction_expected == FlowDirection.INFLOW


def test_model_outage_falls_back_without_crashing():
    agent = WatchAgent(qwen_client=FailingQwenClient())

    result = agent.predict(_notable_signal(confidence=0.4), now=NOW)

    assert result.used_fallback is True
    pred = result.prediction
    assert pred is not None
    assert pred.magnitude_expected == FlowMagnitude.LOW  # confidence 0.4 -> low band


def test_model_probability_is_ignored_even_if_present():
    sneaky = json.dumps(
        {
            "claim": "Outflows accelerate from Coinbase over 12 hours.",
            "realized_direction_expected": "outflow",
            "magnitude_expected": "moderate",
            "evaluation_window_hours": 12,
            "probability": 0.99,
        }
    )
    agent = WatchAgent(qwen_client=StubQwenClient([sneaky]))

    result = agent.predict(_notable_signal(confidence=0.6), now=NOW)

    # extra `probability` key is ignored; derived value used instead.
    assert result.prediction.probability == 0.6


def test_unknown_source_signal_type_is_skipped_not_crashed():
    agent = WatchAgent(qwen_client=StubQwenClient([VALID_MODEL_JSON]))

    result = agent.predict(_notable_signal(signal_type="not_a_real_type"), now=NOW)

    assert result.prediction is None
    assert "unknown signal_type" in result.skipped_reason
