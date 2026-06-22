"""Loop 8: Bridge Signal Synthesis job.

Reads recent NavigationSignals where signal_type is bridge-related and/or the
destination or origin contains bridge protocol names, then synthesises a
cross_chain_bridge_flow summary NavigationSignal.

This is deterministic: no LLM call is made. The synthesis uses aggregated
signal evidence to emit a cross_chain_bridge_flow signal that downstream
agents can use to understand net capital flow across bridge routes.
"""
from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Sequence
from uuid import uuid4

from clients.clickhouse_client import ClickHouseClient
from schemas.navigation_signal import NavigationSignal
from schemas.shared_enums import RiskLevel, SignalStrength
from settings import MapsRunnerSettings

LOOKBACK_HOURS: int = int(os.environ.get("MAPS_BRIDGE_LOOKBACK_HOURS", "6"))
MIN_BRIDGE_SIGNALS: int = int(os.environ.get("MAPS_BRIDGE_MIN_SIGNALS", "3"))

BRIDGE_KEYWORDS = frozenset({
    "bridge", "stargate", "layerzero", "across", "hop", "synapse",
    "wormhole", "ccip", "axelar", "polygon bridge", "arbitrum bridge",
    "optimism bridge",
})

BRIDGE_SIGNAL_TYPES = frozenset({
    "cross_chain_bridge_flow",
    "capital_rotation",
    "route_emergence",
    "route_closure",
})


def _is_bridge_signal(row: dict) -> bool:
    if row.get("signal_type") in BRIDGE_SIGNAL_TYPES:
        return True
    for field in ("origin", "destination", "answer", "question"):
        val = (row.get(field) or "").lower()
        if any(kw in val for kw in BRIDGE_KEYWORDS):
            return True
    return False


def _fetch_recent_signals(
    reader: "Any",
    *,
    since: datetime,
    now: datetime,
) -> list[dict]:
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    return reader.select(
        "SELECT id, signal_type, origin, destination, confidence, risk_level, answer, question "
        "FROM NavigationSignals "
        f"WHERE created_at >= '{since_str}' AND created_at < '{now_str}' "
        "FORMAT JSONEachRow"
    )


def run(
    *,
    dry_run: bool = False,
    now: datetime | None = None,
) -> int:
    from jobs.compute_signal_utility_scores import ClickHouseReadClient  # lazy to avoid UTC import
    settings = MapsRunnerSettings.from_env()
    ts = now or datetime.now(timezone.utc).replace(tzinfo=None)
    since = ts - timedelta(hours=LOOKBACK_HOURS)

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

    all_signals = _fetch_recent_signals(reader, since=since, now=ts)
    bridge_signals = [s for s in all_signals if _is_bridge_signal(s)]

    if len(bridge_signals) < MIN_BRIDGE_SIGNALS:
        return 0

    # Aggregate: top destination, top origin, avg confidence, high risk ratio.
    dest_counts: Counter[str] = Counter(
        s["destination"] for s in bridge_signals if s.get("destination")
    )
    origin_counts: Counter[str] = Counter(
        s["origin"] for s in bridge_signals if s.get("origin")
    )
    confidences = [float(s.get("confidence") or 0.5) for s in bridge_signals]
    avg_confidence = sum(confidences) / len(confidences)
    high_risk_count = sum(
        1 for s in bridge_signals
        if (s.get("risk_level") or "").lower() in ("high", "critical")
    )
    high_risk_ratio = high_risk_count / len(bridge_signals)
    risk_level = RiskLevel.HIGH if high_risk_ratio >= 0.3 else RiskLevel.LOW

    top_dest = dest_counts.most_common(1)[0][0] if dest_counts else ""
    top_origin = origin_counts.most_common(1)[0][0] if origin_counts else ""
    supporting_ids = [s["id"] for s in bridge_signals if s.get("id")][:20]

    answer = (
        f"Bridge activity synthesis over {LOOKBACK_HOURS}h: "
        f"{len(bridge_signals)} bridge-related signals detected. "
        f"Top inflow destination: {top_dest or 'unknown'}. "
        f"Top outflow origin: {top_origin or 'unknown'}. "
        f"High-risk signal ratio: {high_risk_ratio:.0%}. "
        f"Average confidence: {avg_confidence:.2f}."
    )

    signal = NavigationSignal(
        id=f"navsig_{uuid4().hex[:12]}",
        signal_type="cross_chain_bridge_flow",
        question=(
            "What is the net capital flow pattern across bridge routes "
            f"in the last {LOOKBACK_HOURS} hours?"
        ),
        answer=answer,
        origin=top_origin,
        destination=top_dest,
        asset_scope=[],
        chain_scope=[],
        time_horizon_hours=LOOKBACK_HOURS,
        confidence=round(avg_confidence, 4),
        risk_level=risk_level.value,
        signal_strength=SignalStrength.MODERATE.value,
        market_state="",
        supporting_story_ids=[],
        supporting_thesis_ids=[],
        supporting_action_ids=[],
        supporting_outcome_ids=supporting_ids,
        evidence=[],
        created_by_agent="synthesize_bridge_signals",
        model="",
        adapter="",
        schema_version="1.0",
        outcome_status="pending",
        created_at=ts,
    )
    writer.insert_navigation_signal(signal)
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Synthesize bridge signals into a cross_chain_bridge_flow NavigationSignal.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    count = run(dry_run=args.dry_run)
    print(f"Emitted {count} cross_chain_bridge_flow signal(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
