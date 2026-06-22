"""Loop 7: Story Hypothesis Proposal job.

Gathers low-confidence NavigationSignals, groups them, and invokes
StoryHypothesisAgent to propose new story types for human review.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Sequence

from clients.clickhouse_client import ClickHouseClient
from clients.qwen_client import QwenClient
from settings import MapsRunnerSettings

LOOKBACK_DAYS: int = int(os.environ.get("MAPS_HYPOTHESIS_LOOKBACK_DAYS", "7"))
CONFIDENCE_CEILING: float = float(os.environ.get("MAPS_HYPOTHESIS_CONFIDENCE_CEILING", "0.4"))
MIN_WEAK_SIGNALS: int = int(os.environ.get("MAPS_HYPOTHESIS_MIN_SIGNALS", "10"))

EXISTING_STORY_TYPES = [
    "narrative_acceleration",
    "capital_rotation",
    "defi_protocol_stress",
    "l2_expansion",
    "bridge_activity",
    "whale_accumulation",
    "liquidity_migration",
    "route_emergence",
    "route_closure",
    "route_hazard",
    "market_sentiment_shift",
]


class _DryRunFallbackQwenClient(QwenClient):
    def generate(self, *, prompt: str, **_kwargs: object) -> str:
        return "null"


def _fetch_weak_signals(
    reader: "Any",
    *,
    since: datetime,
    now: datetime,
    confidence_ceiling: float,
) -> list[dict]:
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    return reader.select(
        "SELECT id, signal_type, question, answer, confidence, origin, destination, evidence_json "
        "FROM NavigationSignals "
        f"WHERE created_at >= '{since_str}' AND created_at < '{now_str}' "
        f"AND confidence < {confidence_ceiling} "
        "ORDER BY created_at DESC "
        "LIMIT 200 "
        "FORMAT JSONEachRow"
    )


def run(
    *,
    dry_run: bool = False,
    qwen_client: QwenClient | None = None,
    now: datetime | None = None,
) -> int:
    from jobs.compute_signal_utility_scores import ClickHouseReadClient  # lazy to avoid UTC import
    from agents.story_hypothesis_agent import StoryHypothesisAgent
    settings = MapsRunnerSettings.from_env()
    ts = now or datetime.now(timezone.utc).replace(tzinfo=None)
    since = ts - timedelta(days=LOOKBACK_DAYS)

    reader = ClickHouseReadClient(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        database=settings.clickhouse_database,
        username=settings.clickhouse_username,
        password=settings.clickhouse_password,
        secure=settings.clickhouse_secure,
        timeout=settings.clickhouse_timeout,
    )
    writer = ClickHouseClient(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        database=settings.clickhouse_database,
        username=settings.clickhouse_username,
        password=settings.clickhouse_password,
        secure=settings.clickhouse_secure,
        timeout=settings.clickhouse_timeout,
        dry_run=dry_run,
    )
    client = qwen_client or (
        _DryRunFallbackQwenClient() if dry_run else QwenClient.from_env()
    )
    agent = StoryHypothesisAgent(qwen_client=client)

    weak_signals = _fetch_weak_signals(
        reader,
        since=since,
        now=ts,
        confidence_ceiling=CONFIDENCE_CEILING,
    )
    if len(weak_signals) < MIN_WEAK_SIGNALS:
        return 0

    # Pass minimal signal fields to reduce context size.
    context_signals = []
    for row in weak_signals:
        evidence = []
        raw_ev = row.get("evidence_json") or ""
        if raw_ev:
            try:
                evidence = json.loads(raw_ev)
            except (ValueError, TypeError):
                pass
        context_signals.append({
            "id": row.get("id", ""),
            "signal_type": row.get("signal_type", ""),
            "question": row.get("question", ""),
            "answer": row.get("answer", "")[:200],
            "confidence": row.get("confidence", 0.0),
            "origin": row.get("origin", ""),
            "destination": row.get("destination", ""),
            "evidence": evidence[:3],
        })

    result = agent.propose({
        "weak_signals": context_signals,
        "existing_story_types": EXISTING_STORY_TYPES,
        "signal_count": len(weak_signals),
        "lookback_days": LOOKBACK_DAYS,
    })

    if result.hypothesis:
        writer.insert_story_hypothesis(result.hypothesis)
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Propose new story type hypotheses.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    count = run(dry_run=args.dry_run)
    print(f"Proposed {count} story hypothesis/hypotheses.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
