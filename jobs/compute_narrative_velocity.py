"""Loop 3: Narrative Velocity Tracking job.

Deterministically computes the acceleration of each active narrative (story type)
from NavigationSignal history and writes a narrative_acceleration NavigationSignal
when velocity is anomalously high.

No LLM is involved — velocity is a rate computed from signal counts over time.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Sequence
from uuid import uuid4

from clients.clickhouse_client import ClickHouseClient
from schemas.navigation_signal import NavigationSignal
from schemas.shared_enums import RiskLevel, SignalStrength
from settings import MapsRunnerSettings

SHORT_WINDOW_HOURS: int = int(os.environ.get("MAPS_VELOCITY_SHORT_WINDOW_HOURS", "6"))
LONG_WINDOW_HOURS: int = int(os.environ.get("MAPS_VELOCITY_LONG_WINDOW_HOURS", "24"))
VELOCITY_SPIKE_THRESHOLD: float = float(
    os.environ.get("MAPS_VELOCITY_SPIKE_THRESHOLD", "2.5")
)
MIN_SIGNALS_TO_QUALIFY: int = int(os.environ.get("MAPS_VELOCITY_MIN_SIGNALS", "3"))


def _fetch_signal_counts(
    reader: "Any",
    *,
    since: datetime,
    now: datetime,
) -> list[dict]:
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    return reader.select(
        f"SELECT signal_type, count() AS cnt "
        f"FROM NavigationSignals "
        f"WHERE created_at >= '{since_str}' AND created_at < '{now_str}' "
        f"GROUP BY signal_type "
        f"FORMAT JSONEachRow"
    )


def run(
    *,
    dry_run: bool = False,
    now: datetime | None = None,
) -> int:
    from jobs.compute_signal_utility_scores import ClickHouseReadClient  # lazy to avoid UTC import
    settings = MapsRunnerSettings.from_env()
    ts = now or datetime.now(timezone.utc).replace(tzinfo=None)

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

    short_start = ts - timedelta(hours=SHORT_WINDOW_HOURS)
    long_start = ts - timedelta(hours=LONG_WINDOW_HOURS)

    short_counts = {
        r["signal_type"]: int(r["cnt"])
        for r in _fetch_signal_counts(reader, since=short_start, now=ts)
    }
    long_counts = {
        r["signal_type"]: int(r["cnt"])
        for r in _fetch_signal_counts(reader, since=long_start, now=ts)
    }

    emitted = 0
    for signal_type, short_count in short_counts.items():
        if short_count < MIN_SIGNALS_TO_QUALIFY:
            continue
        long_count = long_counts.get(signal_type, 0)
        if long_count == 0:
            continue
        # Normalise to per-hour rates before comparing.
        short_rate = short_count / SHORT_WINDOW_HOURS
        long_rate = long_count / LONG_WINDOW_HOURS
        if long_rate == 0:
            continue
        velocity_ratio = short_rate / long_rate
        if velocity_ratio < VELOCITY_SPIKE_THRESHOLD:
            continue

        # Clamp confidence: ratio 2.5→0.55, ratio 5.0+→0.80
        confidence = min(0.80, 0.55 + (velocity_ratio - VELOCITY_SPIKE_THRESHOLD) * 0.05)

        signal = NavigationSignal(
            id=f"navsig_{uuid4().hex[:12]}",
            signal_type="narrative_acceleration",
            question=(
                f"Is the '{signal_type}' narrative accelerating unusually fast?"
            ),
            answer=(
                f"The '{signal_type}' signal type is generating signals at "
                f"{velocity_ratio:.1f}× its 24h baseline rate "
                f"({short_count} signals in {SHORT_WINDOW_HOURS}h vs "
                f"{long_count} signals in {LONG_WINDOW_HOURS}h). "
                "This narrative is accelerating. Monitor for crowding and confidence decay."
            ),
            asset_scope=[],
            chain_scope=[],
            time_horizon_hours=SHORT_WINDOW_HOURS,
            confidence=confidence,
            risk_level=RiskLevel.MEDIUM.value,
            signal_strength=SignalStrength.MODERATE.value,
            market_state="",
            supporting_story_ids=[],
            supporting_thesis_ids=[],
            supporting_action_ids=[],
            supporting_outcome_ids=[],
            evidence=[],
            created_by_agent="compute_narrative_velocity",
            model="",
            adapter="",
            schema_version="1.0",
            outcome_status="pending",
            created_at=ts,
        )
        writer.insert_navigation_signal(signal)
        emitted += 1

    return emitted


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Compute narrative velocity and emit acceleration signals.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    count = run(dry_run=args.dry_run)
    print(f"Emitted {count} narrative_acceleration signal(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
