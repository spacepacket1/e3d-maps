from __future__ import annotations

import json

import pytest

from agents.base_agent import AgentParseError, AgentValidationError, BaseAgent
from agents.capital_migration_agent import CapitalMigrationAgent
from agents.congestion_agent import CongestionAgent
from agents.destination_prediction_agent import DestinationPredictionAgent
from agents.route_hazard_agent import RouteHazardAgent
from clients.qwen_client import QwenClient
from tests.unit.payloads import navigation_signal_payload, route_prediction_payload


class StubQwenClient(QwenClient):
    def __init__(self, response_text: str) -> None:
        super().__init__(request_executor=lambda request, timeout: b"")
        self.response_text = response_text
        self.calls: list[dict[str, object]] = []

    def generate(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return self.response_text


def fixture_context():
    return {
        "recent_stories": [
            {
                "id": "story_123",
                "story_type": "stablecoin_activity",
                "summary": "Stablecoin inflows increased into Ethereum DeFi wallets.",
                "timestamp": "2026-06-08T00:00:00Z",
            }
        ],
        "recent_theses": [
            {
                "id": "thesis_789",
                "summary": "ETH DeFi is regaining traction.",
                "direction": "bullish",
                "conviction": "medium",
            }
        ],
        "stablecoin_activity": {"netflow": "positive"},
        "exchange_flows": {"ETH": {"netflow": "outflow"}},
        "wallet_cluster_activity": [{"cluster": "smart_money", "destination": "AAVE"}],
        "prior_signals": [{"id": "navsig_prev", "signal_type": "capital_migration"}],
        "market_state": {"label": "risk_on", "rationale": "capital rotating into DeFi"},
        "time_horizon_hours": 24,
    }


def test_base_agent_runs_against_fixture_context():
    client = StubQwenClient(json.dumps(navigation_signal_payload()))
    agent = BaseAgent(
        agent_name="test_agent",
        question_template="Where is capital likely moving over the next {time_horizon_hours} hours?",
        system_prompt="Return JSON only.",
        agent_prompt="Use the provided context.",
        qwen_client=client,
        signal_type="capital_migration",
        adapter_name="base-v0",
    )

    result = agent.run(fixture_context())

    assert result.navigation_signal is not None
    assert result.navigation_signal.signal_type == "capital_migration"
    assert result.route_predictions == ()
    assert "Context JSON:" in client.calls[0]["prompt"]


def test_base_agent_catches_invalid_json():
    client = StubQwenClient("{bad json")
    agent = BaseAgent(
        agent_name="test_agent",
        question_template="Where is capital likely moving over the next {time_horizon_hours} hours?",
        system_prompt="Return JSON only.",
        agent_prompt="Use the provided context.",
        qwen_client=client,
        signal_type="capital_migration",
    )

    with pytest.raises(AgentParseError, match="invalid JSON"):
        agent.run(fixture_context())


def test_base_agent_rejects_invalid_schema_output():
    invalid_payload = navigation_signal_payload()
    invalid_payload.pop("answer")

    client = StubQwenClient(json.dumps(invalid_payload))
    agent = BaseAgent(
        agent_name="test_agent",
        question_template="Where is capital likely moving over the next {time_horizon_hours} hours?",
        system_prompt="Return JSON only.",
        agent_prompt="Use the provided context.",
        qwen_client=client,
        signal_type="capital_migration",
    )

    with pytest.raises(AgentValidationError):
        agent.validate_output(agent.parse_json(client.response_text), question="Where?")


def test_capital_migration_agent_extracts_route_predictions_and_links_signal_id():
    client = StubQwenClient(
        json.dumps(
            {
                "navigation_signal": navigation_signal_payload(id="navsig_cap_001"),
                "route_predictions": [
                    route_prediction_payload(
                        id="route_001",
                        navigation_signal_id="",
                        created_at="2026-06-08T00:00:00Z",
                    )
                ],
            }
        )
    )
    agent = CapitalMigrationAgent(qwen_client=client)

    result = agent.run(fixture_context())

    assert result.navigation_signal is not None
    assert result.navigation_signal.origin == "stablecoins"
    assert result.navigation_signal.destination == "ETH_DEFI"
    assert result.navigation_signal.time_horizon_hours == 24
    assert result.navigation_signal.evidence
    assert len(result.route_predictions) == 1
    assert result.route_predictions[0].navigation_signal_id == "navsig_cap_001"


def test_capital_migration_agent_returns_null_when_evidence_is_insufficient():
    client = StubQwenClient("null")
    agent = CapitalMigrationAgent(qwen_client=client)

    result = agent.run(fixture_context())

    assert result.navigation_signal is None
    assert result.route_predictions == ()


def test_congestion_agent_validates_congestion_signal():
    payload = navigation_signal_payload(
        signal_type="congestion_formation",
        question="Where is congestion forming right now?",
        answer="Crowding is building in meme-token venues.",
        origin="MEME_TOKENS",
        destination="CEX",
        risk_level="high",
    )
    client = StubQwenClient(json.dumps(payload))

    result = CongestionAgent(qwen_client=client).run(fixture_context())

    assert result.navigation_signal is not None
    assert result.navigation_signal.signal_type == "congestion_formation"


def test_route_hazard_agent_accepts_route_closure_signal():
    payload = navigation_signal_payload(
        signal_type="route_closure",
        question="What route hazards or closures are forming over the next 24 hours?",
        answer="A route into a bridge venue appears to be closing due to deteriorating liquidity.",
        origin="stablecoins",
        destination="BASE_DEFI",
        risk_level="critical",
    )
    client = StubQwenClient(json.dumps(payload))

    result = RouteHazardAgent(qwen_client=client).run(fixture_context())

    assert result.navigation_signal is not None
    assert result.navigation_signal.signal_type == "route_closure"


def test_destination_prediction_agent_returns_signal_and_route_predictions():
    payload = {
        "navigation_signal": navigation_signal_payload(
            id="navsig_dest_001",
            signal_type="destination_prediction",
            question="Which destination is gaining probability over the next 24 hours?",
            answer="ETH DeFi is the likeliest near-term destination for incoming capital.",
        ),
        "route_predictions": [
            route_prediction_payload(
                id="route_dest_001",
                navigation_signal_id="navsig_dest_001",
            )
        ],
    }
    client = StubQwenClient(json.dumps(payload))

    result = DestinationPredictionAgent(qwen_client=client).run(fixture_context())

    assert result.navigation_signal is not None
    assert result.navigation_signal.signal_type == "destination_prediction"
    assert len(result.route_predictions) == 1
    assert result.route_predictions[0].navigation_signal_id == "navsig_dest_001"
