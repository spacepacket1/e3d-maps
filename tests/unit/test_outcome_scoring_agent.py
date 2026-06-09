from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from agents.base_agent import AgentParseError, AgentValidationError
from agents.outcome_scoring_agent import OutcomeScoringAgent
from clients.qwen_client import QwenClient
from schemas.navigation_signal import NavigationSignal
from schemas.prediction_outcome import PredictionOutcome
from tests.unit.payloads import navigation_signal_payload


class StubQwenClient(QwenClient):
    def __init__(self, response_text: str) -> None:
        super().__init__(request_executor=lambda request, timeout: b"")
        self.response_text = response_text

    def generate(self, **kwargs) -> str:
        return self.response_text


def fixture_signal() -> NavigationSignal:
    return NavigationSignal.model_validate(navigation_signal_payload(id="navsig_test_001"))


def fixture_evidence_context():
    return {
        "stories": [
            {
                "id": "story_post_001",
                "story_type": "capital_migration",
                "summary": "ETH DeFi inflows confirmed after signal period.",
                "origin": "stablecoins",
                "destination": "ETH_DEFI",
                "timestamp": "2026-06-09T06:00:00Z",
            }
        ],
        "exchange_flows": [
            {
                "asset": "ETH",
                "direction": "inflow",
                "timestamp": "2026-06-09T08:00:00Z",
            }
        ],
        "stablecoin_activity": [
            {
                "netflow": "positive",
                "direction": "inflow",
                "timestamp": "2026-06-09T04:00:00Z",
            }
        ],
    }


def valid_outcome_response():
    return json.dumps({
        "navigation_signal_id": "navsig_test_001",
        "evaluation_window_hours": 24,
        "prediction_accuracy": 0.8,
        "realized_direction": "inflow",
        "realized_magnitude": "moderate",
        "map_prediction_correct": True,
        "notes": "Story story_post_001 confirmed ETH DeFi inflows. Exchange flows consistent.",
        "created_by_agent": "outcome_scoring_agent",
    })


def test_outcome_scoring_agent_returns_prediction_outcome():
    agent = OutcomeScoringAgent(qwen_client=StubQwenClient(valid_outcome_response()))
    signal = fixture_signal()

    result = agent.score(signal=signal, evidence_context=fixture_evidence_context())

    assert isinstance(result, PredictionOutcome)
    assert result.navigation_signal_id == "navsig_test_001"
    assert result.prediction_accuracy == 0.8
    assert result.map_prediction_correct is True
    assert result.realized_direction.value == "inflow"
    assert result.realized_magnitude.value == "moderate"
    assert result.created_by_agent == "outcome_scoring_agent"


def test_outcome_scoring_agent_defaults_navigation_signal_id_from_signal():
    response = json.dumps({
        "evaluation_window_hours": 24,
        "prediction_accuracy": 0.6,
        "realized_direction": "inflow",
        "realized_magnitude": "low",
        "map_prediction_correct": True,
        "notes": "Matched.",
        "created_by_agent": "outcome_scoring_agent",
    })
    agent = OutcomeScoringAgent(qwen_client=StubQwenClient(response))
    signal = fixture_signal()

    result = agent.score(signal=signal, evidence_context={})

    assert result.navigation_signal_id == "navsig_test_001"


def test_outcome_scoring_agent_defaults_evaluation_window_from_signal():
    response = json.dumps({
        "navigation_signal_id": "navsig_test_001",
        "prediction_accuracy": 0.4,
        "realized_direction": "outflow",
        "realized_magnitude": "low",
        "map_prediction_correct": False,
        "notes": "Did not match.",
        "created_by_agent": "outcome_scoring_agent",
    })
    agent = OutcomeScoringAgent(qwen_client=StubQwenClient(response))
    signal = fixture_signal()

    result = agent.score(signal=signal, evidence_context={})

    assert result.evaluation_window_hours == 24


def test_outcome_scoring_agent_sets_created_at_when_missing():
    response = json.dumps({
        "navigation_signal_id": "navsig_test_001",
        "evaluation_window_hours": 24,
        "prediction_accuracy": 0.5,
        "realized_direction": "neutral",
        "realized_magnitude": "low",
        "map_prediction_correct": False,
        "notes": "Neutral.",
        "created_by_agent": "outcome_scoring_agent",
    })
    agent = OutcomeScoringAgent(qwen_client=StubQwenClient(response))
    signal = fixture_signal()

    result = agent.score(signal=signal, evidence_context={})

    assert result.created_at is not None


def test_outcome_scoring_agent_rejects_invalid_json():
    agent = OutcomeScoringAgent(qwen_client=StubQwenClient("{bad json"))
    signal = fixture_signal()

    with pytest.raises(AgentParseError, match="invalid JSON"):
        agent.score(signal=signal, evidence_context={})


def test_outcome_scoring_agent_rejects_non_object_response():
    agent = OutcomeScoringAgent(qwen_client=StubQwenClient(json.dumps([0.8, True])))
    signal = fixture_signal()

    with pytest.raises(AgentValidationError, match="JSON object"):
        agent.score(signal=signal, evidence_context={})


def test_outcome_scoring_agent_rejects_invalid_schema():
    response = json.dumps({
        "navigation_signal_id": "navsig_test_001",
        "evaluation_window_hours": 24,
        "prediction_accuracy": 1.5,
        "realized_direction": "inflow",
        "realized_magnitude": "moderate",
        "map_prediction_correct": True,
        "notes": "Bad accuracy.",
        "created_by_agent": "outcome_scoring_agent",
    })
    agent = OutcomeScoringAgent(qwen_client=StubQwenClient(response))
    signal = fixture_signal()

    with pytest.raises(AgentValidationError, match="invalid PredictionOutcome"):
        agent.score(signal=signal, evidence_context={})
