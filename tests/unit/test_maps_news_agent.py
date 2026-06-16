from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from agents.maps_news_agent import MapsNewsAgent
from clients.qwen_client import QwenClient
from schemas.cross_chain_activity_state import CrossChainActivityState
from schemas.maps_news_brief import MapsNewsBrief
from schemas.navigation_signal import NavigationSignal
from schemas.traffic_state import TrafficState
from tests.unit.payloads import (
    cross_chain_activity_state_payload,
    maps_news_brief_payload,
    navigation_signal_payload,
)


class StubQwenClient(QwenClient):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(request_executor=lambda request, timeout: b"")
        self._responses = list(responses)

    def generate(self, **kwargs) -> str:
        return self._responses.pop(0)


BASE_TIME = datetime(2026, 6, 16, 12, 0, tzinfo=UTC)


def _make_signal(**overrides) -> NavigationSignal:
    payload = navigation_signal_payload(
        id=overrides.pop("id", "navsig_test_1"),
        signal_type=overrides.pop("signal_type", "route_hazard"),
        answer=overrides.pop(
            "answer",
            "Bridge-linked Ethereum routes are active, but hazard signals are rising into Base.",
        ),
        origin=overrides.pop("origin", "ETH_DEFI"),
        destination=overrides.pop("destination", "BASE"),
        confidence=overrides.pop("confidence", 0.82),
        risk_level=overrides.pop("risk_level", "high"),
        created_at=overrides.pop("created_at", BASE_TIME.isoformat()),
        supporting_story_ids=overrides.pop("supporting_story_ids", ["story_123"]),
        supporting_thesis_ids=overrides.pop("supporting_thesis_ids", ["thesis_789"]),
    )
    payload.update(overrides)
    return NavigationSignal.model_validate(payload)


def _make_traffic_state(**overrides) -> TrafficState:
    payload = {
        "id": "traffic_01",
        "scope": "global",
        "market_state": "risk_on",
        "dominant_flows": [
            {"origin": "stablecoins", "destination": "ETH_DEFI", "strength": "strong"}
        ],
        "congestion_zones": ["BASE"],
        "hazards": ["route_hazard: BASE"],
        "top_destinations": [{"destination": "ETH_DEFI", "confidence": 0.74}],
        "created_by_agent": "traffic_state_assembler",
        "created_at": BASE_TIME.isoformat(),
    }
    payload.update(overrides)
    return TrafficState.model_validate(payload)


def _make_cross_chain_state(**overrides) -> CrossChainActivityState:
    payload = cross_chain_activity_state_payload(
        id="ccas_01",
        market_bias="risk_on",
        created_at=BASE_TIME.isoformat(),
    )
    payload.update(overrides)
    return CrossChainActivityState.model_validate(payload)


def _make_previous_brief(**overrides) -> MapsNewsBrief:
    payload = maps_news_brief_payload(
        id="brief_prev",
        created_at=(BASE_TIME - timedelta(hours=4)).isoformat(),
    )
    payload.update(overrides)
    return MapsNewsBrief.model_validate(payload)


def test_valid_model_response_parses_maps_news_brief():
    qwen_client = StubQwenClient(
        [
            json.dumps(
                {
                    "headline": "Ethereum flows remain active, but Base-bound routes are getting more crowded",
                    "summary": (
                        "Ethereum-linked demand is still showing up in the strongest route set, but Base "
                        "traffic is carrying fresh hazard and congestion evidence that points to weaker route "
                        "quality. The broader market_bias stays risk_on, yet the featured signals argue for a "
                        "more selective read on execution conditions."
                    ),
                    "stance": "crowded",
                    "tags": ["ethereum", "base", "congestion"],
                    "supporting_signal_ids": ["navsig_test_1", "navsig_test_2"],
                    "supporting_story_ids": ["story_123", "story_456"],
                    "supporting_thesis_ids": ["thesis_789"],
                }
            )
        ]
    )
    agent = MapsNewsAgent(qwen_client=qwen_client)

    result = agent.run(
        {
            "traffic_state": _make_traffic_state(),
            "cross_chain_activity_state": _make_cross_chain_state(),
            "previous_brief": _make_previous_brief(),
            "recent_signals": [
                _make_signal(id="navsig_test_1"),
                _make_signal(
                    id="navsig_test_2",
                    signal_type="congestion_formation",
                    confidence=0.76,
                    risk_level="medium",
                    answer="Base-bound traffic is getting more crowded through the main bridge corridor.",
                    supporting_story_ids=["story_456"],
                ),
            ],
        }
    )

    assert result.used_fallback is False
    assert result.brief.stance == "crowded"
    assert result.brief.supporting_signal_ids == ["navsig_test_1", "navsig_test_2"]
    assert result.brief.created_by_agent == "maps_news_agent"


def test_invalid_json_uses_deterministic_fallback_brief():
    qwen_client = StubQwenClient(["not-json"])
    agent = MapsNewsAgent(qwen_client=qwen_client)

    result = agent.run(
        {
            "traffic_state": _make_traffic_state(market_state="risk_off"),
            "cross_chain_activity_state": _make_cross_chain_state(market_bias="risk_off"),
            "recent_signals": [_make_signal(id="navsig_test_1")],
        }
    )

    assert result.used_fallback is True
    assert result.brief.headline == "Routes are active with elevated risk on binance"
    assert "risk off conditions overall" in result.brief.summary
    assert result.brief.stance == "risk_off"
    assert result.brief.supporting_signal_ids == ["navsig_test_1"]


def test_unsupported_references_are_rejected_and_prompt_contains_guardrails():
    qwen_client = StubQwenClient(
        [
            json.dumps(
                {
                    "headline": "Ethereum activity is still live, but unsupported claims should not survive validation",
                    "summary": (
                        "The route set remains active enough to generate a clean brief, but this response "
                        "tries to cite a signal that was never present in the featured evidence. That makes "
                        "the output ungrounded even if the prose itself sounds plausible on first read."
                    ),
                    "stance": "cautious",
                    "tags": ["ethereum"],
                    "supporting_signal_ids": ["navsig_missing"],
                    "supporting_story_ids": [],
                    "supporting_thesis_ids": [],
                }
            )
        ]
    )
    agent = MapsNewsAgent(qwen_client=qwen_client)
    prompt_text = agent.agent_prompt

    result = agent.run(
        {
            "traffic_state": _make_traffic_state(),
            "cross_chain_activity_state": _make_cross_chain_state(),
            "recent_signals": [_make_signal(id="navsig_test_1")],
        }
    )

    assert "stay grounded in provided evidence only" in prompt_text
    assert "avoid mentioning assets, chains, venues, or bridges that are absent from the input" in prompt_text
    assert result.used_fallback is True
    assert "featured signal context" in (result.fallback_reason or "")
