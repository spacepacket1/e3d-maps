from __future__ import annotations

import json
from datetime import datetime
from urllib.error import HTTPError

from clients.e3d_api_client import E3DAPIClient


def test_get_recent_stories_uses_limit_and_bounds_results():
    captured = {}

    def request_executor(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return json.dumps(
            {
                "stories": [
                    {"id": "story_3"},
                    {"id": "story_2"},
                    {"id": "story_1"},
                ]
            }
        ).encode("utf-8")

    client = E3DAPIClient(
        base_url="https://api.e3d.ai",
        timeout=3.5,
        request_executor=request_executor,
    )

    stories = client.get_recent_stories(max_items=2)

    assert stories == [{"id": "story_3"}, {"id": "story_2"}]
    assert captured["url"] == "https://api.e3d.ai/api/stories?limit=2"
    assert captured["timeout"] == 3.5


def test_get_recent_theses_handles_missing_payload_gracefully():
    def request_executor(request, timeout):
        raise HTTPError(request.full_url, 404, "Not Found", hdrs=None, fp=None)

    client = E3DAPIClient(request_executor=request_executor)

    assert client.get_recent_theses() == []


def test_get_market_context_trims_inputs_to_budget_in_priority_order():
    responses = {
        "https://e3d.ai/api/stories?limit=4": {"stories": [{"id": f"story_{index}", "summary": "s" * 120} for index in range(4)]},
        "https://e3d.ai/api/theses?limit=3": {"theses": [{"id": f"thesis_{index}", "summary": "t" * 120} for index in range(3)]},
        "https://e3d.ai/api/wallets/activity?limit=2": {"items": [{"id": f"wallet_{index}", "summary": "w" * 120} for index in range(2)]},
        "https://e3d.ai/api/tokens/activity?limit=1": {"items": [{"id": "token_1", "summary": "x" * 120}]},
        "https://e3d.ai/api/flows/exchange?limit=2": {"items": [{"id": f"flow_{index}", "summary": "f" * 120} for index in range(2)]},
        "https://e3d.ai/api/market/context": {"state": "risk_on"},
    }

    def request_executor(request, timeout):
        return json.dumps(responses[request.full_url]).encode("utf-8")

    client = E3DAPIClient(request_executor=request_executor)
    context = client.get_market_context(
        stories_max_items=4,
        theses_max_items=3,
        wallet_activity_max_items=2,
        token_activity_max_items=1,
        exchange_flows_max_items=2,
        prior_signals=[{"id": "navsig_1", "answer": "p" * 120}],
        token_budget=120,
    )

    assert client._estimate_tokens(context) <= 120
    assert context["prior_signals"] == []
    assert context["recent_theses"] == []
    assert context["wallet_activity"] == []
    assert context["exchange_flows"] == []
    assert len(context["recent_stories"]) < 4
    assert context["token_activity"] == [{"id": "token_1", "summary": "x" * 120}]
    assert context["market_state"] == {"state": "risk_on"}


def test_get_json_retries_transient_failures():
    attempts = {"count": 0}

    def request_executor(request, timeout):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise HTTPError(request.full_url, 503, "Unavailable", hdrs=None, fp=None)
        return json.dumps({"stories": [{"id": "story_1"}]}).encode("utf-8")

    client = E3DAPIClient(
        request_executor=request_executor,
        max_retries=2,
        retry_backoff_seconds=0,
    )

    stories = client.get_recent_stories(max_items=5)

    assert stories == [{"id": "story_1"}]
    assert attempts["count"] == 3


def test_windowed_context_methods_include_time_bounds():
    captured = []
    payloads = [
        {"stories": [{"id": "story_1"}]},
        {"items": [{"id": "row_1"}]},
        {"items": [{"id": "row_1"}]},
    ]

    def request_executor(request, timeout):
        captured.append(request.full_url)
        return json.dumps(payloads[len(captured) - 1]).encode("utf-8")

    client = E3DAPIClient(
        base_url="https://api.e3d.ai",
        request_executor=request_executor,
    )

    start_time = "2026-06-08T00:00:00Z"
    end_time = "2026-06-09T00:00:00Z"

    stories = client.get_stories_within_window(
        start_time=datetime.fromisoformat(start_time.replace("Z", "+00:00")),
        end_time=datetime.fromisoformat(end_time.replace("Z", "+00:00")),
        max_items=3,
    )
    exchange_flows = client.get_exchange_flows_within_window(
        start_time=datetime.fromisoformat(start_time.replace("Z", "+00:00")),
        end_time=datetime.fromisoformat(end_time.replace("Z", "+00:00")),
        max_items=4,
    )
    stablecoin_activity = client.get_stablecoin_activity_within_window(
        start_time=datetime.fromisoformat(start_time.replace("Z", "+00:00")),
        end_time=datetime.fromisoformat(end_time.replace("Z", "+00:00")),
        max_items=5,
    )

    assert stories == [{"id": "story_1"}]
    assert exchange_flows == [{"id": "row_1"}]
    assert stablecoin_activity == [{"id": "row_1"}]
    assert captured[0] == (
        "https://api.e3d.ai/api/stories?limit=3"
        "&time_min=2026-06-08T00%3A00%3A00Z"
        "&time_max=2026-06-09T00%3A00%3A00Z"
    )
    assert captured[1] == (
        "https://api.e3d.ai/api/flows/exchange?limit=4"
        "&time_min=2026-06-08T00%3A00%3A00Z"
        "&time_max=2026-06-09T00%3A00%3A00Z"
    )
    assert captured[2] == (
        "https://api.e3d.ai/api/tokens/activity?limit=5"
        "&time_min=2026-06-08T00%3A00%3A00Z"
        "&time_max=2026-06-09T00%3A00%3A00Z"
    )
