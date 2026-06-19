from __future__ import annotations

import io

from clients.clickhouse_client import ClickHouseClient
from jobs import run_watch_agent
from schemas.watch_draft import WatchDraft
from schemas.watch_prediction import WatchPrediction


class FakeFeed:
    def __init__(self, notable):
        self._notable = notable
        self.calls = []

    def get_notable(self, *, min_score, since=None, limit=50):
        self.calls.append({"min_score": min_score, "since": since, "limit": limit})
        return list(self._notable)[:limit]

    def get_calibration(self, *, source="watch_agent"):
        return {"overall": {"hit_rate": 0.66, "total_scored": 120}}


def _notable(**overrides):
    item = {
        "signal_id": "navsig_01J",
        "signal_type": "capital_migration",
        "asset_scope": ["ETH"],
        "chain_scope": ["ethereum"],
        "confidence": 0.8,
        "notability": 80,
        "summary": "ETH rotating into Coinbase, sell-side liquidity building.",
    }
    item.update(overrides)
    return item


def test_dry_run_emits_valid_prediction_and_draft_rows():
    feed = FakeFeed([_notable(signal_id="navsig_01J"), _notable(signal_id="navsig_02J")])
    output = io.StringIO()

    writer = ClickHouseClient(dry_run=True, output=output)

    # No qwen_client -> dry-run fallback client -> deterministic fallback path.
    result = run_watch_agent.run(
        dry_run=True,
        min_event_score=60,
        candidate_cap=10,
        feed_client=feed,
        writer=writer,
    )

    assert result.candidates == 2
    assert result.predictions_written == 2
    assert result.drafts_written == 2
    assert feed.calls[0]["min_score"] == 60
    # Rows are validated models.
    assert all(isinstance(p, WatchPrediction) for p in result.predictions)
    assert all(isinstance(d, WatchDraft) for d in result.drafts)
    # Dry-run forces deterministic fallbacks on both stages.
    assert result.used_fallback_predictions == 2
    assert result.used_fallback_drafts == 2

    # Both tables were written in dry-run.
    text = output.getvalue()
    assert "WatchPredictions" in text
    assert "WatchDrafts" in text


def test_candidate_cap_bounds_processing():
    feed = FakeFeed([_notable(signal_id=f"navsig_{i}") for i in range(10)])

    writer = ClickHouseClient(dry_run=True, output=io.StringIO())

    result = run_watch_agent.run(
        dry_run=True,
        candidate_cap=3,
        feed_client=feed,
        writer=writer,
    )

    assert feed.calls[0]["limit"] == 3
    assert result.predictions_written == 3


def test_unknown_signal_type_is_skipped_not_written():
    feed = FakeFeed([_notable(signal_id="navsig_01J", signal_type="not_a_type")])

    writer = ClickHouseClient(dry_run=True, output=io.StringIO())

    result = run_watch_agent.run(dry_run=True, feed_client=feed, writer=writer)

    assert result.skipped == 1
    assert result.predictions_written == 0


def test_duplicate_idempotency_keys_are_written_once():
    # Two identical notable signals -> same idempotency key -> one prediction.
    feed = FakeFeed([_notable(signal_id="navsig_01J"), _notable(signal_id="navsig_01J")])

    writer = ClickHouseClient(dry_run=True, output=io.StringIO())

    result = run_watch_agent.run(dry_run=True, feed_client=feed, writer=writer)

    assert result.candidates == 2
    assert result.predictions_written == 1
