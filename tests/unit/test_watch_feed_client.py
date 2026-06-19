from __future__ import annotations

import json

from clients.watch_feed_client import WatchFeedClient


def _make_executor(responses):
    """Build a request_executor returning queued JSON payloads, capturing requests."""
    captured = []
    queue = list(responses)

    def request_executor(request, timeout):
        captured.append(request)
        payload = queue.pop(0)
        return json.dumps(payload).encode("utf-8")

    return request_executor, captured


def test_get_notable_parses_items_and_sends_bearer_auth():
    executor, captured = _make_executor(
        [
            {
                "status": "ok",
                "notable": [
                    {"signal_id": "navsig_01J", "notability": 80, "created_at": "2026-06-08 00:00:00"},
                    {"signal_id": "navsig_02J", "notability": 72, "created_at": "2026-06-08 01:00:00"},
                ],
                "pagination": {"count": 2},
            }
        ]
    )
    client = WatchFeedClient(
        base_url="https://maps.e3d.ai",
        api_key="secret-token",
        request_executor=executor,
        retry_backoff_seconds=0,
    )

    items = client.get_notable(min_score=60, limit=10)

    assert [i["signal_id"] for i in items] == ["navsig_01J", "navsig_02J"]
    request = captured[0]
    assert request.full_url.startswith("https://maps.e3d.ai/api/maps/notable")
    assert "min_score=60" in request.full_url
    # Public-contract hygiene: Bearer auth, not the internal x-api-key.
    assert request.headers.get("Authorization") == "Bearer secret-token"
    assert "X-api-key" not in request.headers


def test_get_notable_advances_cursor_so_events_are_not_reprocessed():
    executor, captured = _make_executor(
        [
            {
                "notable": [
                    {"signal_id": "a", "created_at": "2026-06-08 00:00:00"},
                    {"signal_id": "b", "created_at": "2026-06-08 02:00:00"},
                ]
            },
            {
                "notable": [
                    {"signal_id": "c", "created_at": "2026-06-08 03:00:00"},
                ]
            },
        ]
    )
    client = WatchFeedClient(
        base_url="https://maps.e3d.ai",
        request_executor=executor,
        retry_backoff_seconds=0,
    )

    first = client.get_notable(limit=10)
    assert len(first) == 2
    # Cursor advanced to the newest created_at from the first batch.
    assert client.notable_cursor == "2026-06-08 02:00:00"

    # Second call carries the cursor forward as `since` automatically.
    client.get_notable(limit=10)
    second_url = captured[1].full_url
    assert "since=2026-06-08" in second_url
    assert "02%3A00%3A00" in second_url
    assert client.notable_cursor == "2026-06-08 03:00:00"


def test_get_signal_and_calibration_unwrap_envelopes():
    executor, _ = _make_executor(
        [
            {"status": "ok", "signal": {"id": "navsig_01J", "signal_type": "capital_migration"}},
            {"status": "ok", "calibration": {"overall": {"hit_rate": 0.71}}},
        ]
    )
    client = WatchFeedClient(request_executor=executor, retry_backoff_seconds=0)

    signal = client.get_signal("navsig_01J")
    assert signal["signal_type"] == "capital_migration"

    calibration = client.get_calibration(source="watch_agent")
    assert calibration["overall"]["hit_rate"] == 0.71


def test_missing_endpoints_return_safe_empty_values():
    def executor(request, timeout):
        from urllib.error import HTTPError

        raise HTTPError(request.full_url, 404, "missing", {}, None)

    client = WatchFeedClient(request_executor=executor, retry_backoff_seconds=0)

    assert client.get_notable() == []
    assert client.get_signal("missing") is None
    assert client.get_calibration() == {}
