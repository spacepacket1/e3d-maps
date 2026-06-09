from __future__ import annotations

import json

import pytest

from agents.confidence_scoring_agent import ConfidenceAssessment, ConfidenceScoringAgent
from agents.base_agent import AgentParseError, AgentValidationError
from clients.qwen_client import QwenClient
from tests.unit.payloads import navigation_signal_payload


class StubQwenClient(QwenClient):
    def __init__(self, response_text: str) -> None:
        super().__init__(request_executor=lambda request, timeout: b"")
        self.response_text = response_text

    def generate(self, **kwargs) -> str:
        return self.response_text


def fixture_signal_draft():
    return navigation_signal_payload()


def fixture_context():
    return {
        "recent_stories": [
            {
                "id": "story_123",
                "story_type": "stablecoin_activity",
                "summary": "Stablecoin inflows increased.",
                "timestamp": "2026-06-08T00:00:00Z",
            }
        ],
        "recent_theses": [{"id": "thesis_789", "summary": "ETH DeFi is gaining.", "conviction": "medium"}],
        "stablecoin_activity": {"netflow": "positive"},
        "exchange_flows": {"ETH": {"netflow": "outflow"}},
        "market_state": {"label": "risk_on"},
        "prior_signals": [],
    }


def test_confidence_scoring_agent_returns_assessment_for_valid_response():
    response = json.dumps({
        "confidence": 0.72,
        "confidence_explanation": "Two stories support the thesis. No contradictions.",
        "calibration_notes": "Draft confidence accepted with minor downward adjustment.",
    })
    agent = ConfidenceScoringAgent(qwen_client=StubQwenClient(response))

    result = agent.score(signal_draft=fixture_signal_draft(), context=fixture_context())

    assert isinstance(result, ConfidenceAssessment)
    assert result.confidence == 0.72
    assert "stories" in result.confidence_explanation
    assert result.calibration_notes != ""


def test_confidence_scoring_agent_accepts_floor_value():
    response = json.dumps({
        "confidence": 0.30,
        "confidence_explanation": "Minimal evidence.",
        "calibration_notes": "At floor.",
    })
    agent = ConfidenceScoringAgent(qwen_client=StubQwenClient(response))

    result = agent.score(signal_draft=fixture_signal_draft(), context=fixture_context())

    assert result.confidence == 0.30


def test_confidence_scoring_agent_accepts_ceiling_value():
    response = json.dumps({
        "confidence": 0.90,
        "confidence_explanation": "Exceptional convergence across all sources.",
        "calibration_notes": "At ceiling.",
    })
    agent = ConfidenceScoringAgent(qwen_client=StubQwenClient(response))

    result = agent.score(signal_draft=fixture_signal_draft(), context=fixture_context())

    assert result.confidence == 0.90


def test_confidence_scoring_agent_rejects_invalid_json():
    agent = ConfidenceScoringAgent(qwen_client=StubQwenClient("{bad json"))

    with pytest.raises(AgentParseError, match="invalid JSON"):
        agent.score(signal_draft=fixture_signal_draft(), context=fixture_context())


def test_confidence_scoring_agent_rejects_non_object_response():
    agent = ConfidenceScoringAgent(qwen_client=StubQwenClient(json.dumps([0.72])))

    with pytest.raises(AgentValidationError, match="JSON object"):
        agent.score(signal_draft=fixture_signal_draft(), context=fixture_context())


def test_confidence_scoring_agent_rejects_confidence_above_ceiling():
    response = json.dumps({"confidence": 0.95, "confidence_explanation": "", "calibration_notes": ""})
    agent = ConfidenceScoringAgent(qwen_client=StubQwenClient(response))

    with pytest.raises(AgentValidationError, match="outside"):
        agent.score(signal_draft=fixture_signal_draft(), context=fixture_context())


def test_confidence_scoring_agent_rejects_confidence_below_floor():
    response = json.dumps({"confidence": 0.10, "confidence_explanation": "", "calibration_notes": ""})
    agent = ConfidenceScoringAgent(qwen_client=StubQwenClient(response))

    with pytest.raises(AgentValidationError, match="outside"):
        agent.score(signal_draft=fixture_signal_draft(), context=fixture_context())


def test_confidence_scoring_agent_rejects_non_numeric_confidence():
    response = json.dumps({"confidence": "high", "confidence_explanation": "", "calibration_notes": ""})
    agent = ConfidenceScoringAgent(qwen_client=StubQwenClient(response))

    with pytest.raises(AgentValidationError, match="non-numeric"):
        agent.score(signal_draft=fixture_signal_draft(), context=fixture_context())


def test_confidence_scoring_agent_uses_empty_strings_for_missing_text_fields():
    response = json.dumps({"confidence": 0.65})
    agent = ConfidenceScoringAgent(qwen_client=StubQwenClient(response))

    result = agent.score(signal_draft=fixture_signal_draft(), context=fixture_context())

    assert result.confidence == 0.65
    assert result.confidence_explanation == ""
    assert result.calibration_notes == ""
