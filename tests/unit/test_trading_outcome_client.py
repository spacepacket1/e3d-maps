from __future__ import annotations

import json
from urllib.error import HTTPError

from clients.trading_outcome_client import TradingOutcomeClient


def test_get_recent_actions_bounds_results():
    def request_executor(request, timeout):
        return json.dumps(
            {
                "actions": [
                    {"id": "action_3"},
                    {"id": "action_2"},
                    {"id": "action_1"},
                ]
            }
        ).encode("utf-8")

    client = TradingOutcomeClient(request_executor=request_executor)

    actions = client.get_recent_actions(max_items=2)

    assert actions == [{"id": "action_3"}, {"id": "action_2"}]


def test_get_recent_outcomes_is_optional_when_api_is_missing():
    def request_executor(request, timeout):
        raise HTTPError(request.full_url, 404, "Not Found", hdrs=None, fp=None)

    client = TradingOutcomeClient(request_executor=request_executor)

    assert client.get_recent_outcomes() == []
    assert client.get_recent_verdicts() == []


def test_get_actions_linked_to_navigation_signal_adds_filter():
    captured = {}

    def request_executor(request, timeout):
        captured["url"] = request.full_url
        return json.dumps({"items": [{"id": "action_1", "navigation_signal_ids": ["navsig_1"]}]}).encode(
            "utf-8"
        )

    client = TradingOutcomeClient(request_executor=request_executor)

    linked_actions = client.get_actions_linked_to_navigation_signal("navsig_1", max_items=5)

    assert linked_actions == [{"id": "action_1", "navigation_signal_ids": ["navsig_1"]}]
    assert captured["url"] == (
        "https://e3d.ai/api/trading/actions?navigation_signal_id=navsig_1&limit=5"
    )


def test_get_actions_linked_to_route_prediction_adds_filter():
    captured = {}

    def request_executor(request, timeout):
        captured["url"] = request.full_url
        return json.dumps({"items": [{"id": "action_2", "route_prediction_ids": ["route_1"]}]}).encode(
            "utf-8"
        )

    client = TradingOutcomeClient(request_executor=request_executor)

    linked_actions = client.get_actions_linked_to_route_prediction("route_1", max_items=4)

    assert linked_actions == [{"id": "action_2", "route_prediction_ids": ["route_1"]}]
    assert captured["url"] == (
        "https://e3d.ai/api/trading/actions?route_prediction_id=route_1&limit=4"
    )
