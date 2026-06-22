"""Loop 1: Query Demand Intelligence aggregation job.

Reads QueryAccessLogs for the configured window, aggregates by destination /
signal_type / time_horizon, and writes a SignalDemandState snapshot.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from typing import Sequence
from uuid import uuid4

from clients.clickhouse_client import ClickHouseClient
from schemas.signal_demand_state import (
    DestinationQueryCount,
    SignalDemandState,
    SignalTypeQueryCount,
)
from settings import MapsRunnerSettings

import os as _os

SURGE_MULTIPLIER: float = float(_os.environ.get("MAPS_DEMAND_SURGE_MULTIPLIER", "2.0"))
MIN_BUCKET_SAMPLES: int = int(_os.environ.get("MAPS_DEMAND_MIN_BUCKET_SAMPLES", "3"))


def _fetch_logs(
    reader: "Any",
    *,
    window_start: datetime,
    window_end: datetime,
) -> list[dict]:
    start_str = window_start.strftime("%Y-%m-%d %H:%M:%S")
    end_str = window_end.strftime("%Y-%m-%d %H:%M:%S")
    return reader.select(
        f"SELECT * FROM QueryAccessLogs "
        f"WHERE requested_at >= '{start_str}' AND requested_at < '{end_str}' "
        "FORMAT JSONEachRow"
    )


def _fetch_baseline_logs(
    reader: "Any",
    *,
    window_end: datetime,
    baseline_hours: int = 24,
) -> list[dict]:
    start_str = (window_end - timedelta(hours=baseline_hours)).strftime("%Y-%m-%d %H:%M:%S")
    end_str = window_end.strftime("%Y-%m-%d %H:%M:%S")
    return reader.select(
        f"SELECT destination_filter FROM QueryAccessLogs "
        f"WHERE requested_at >= '{start_str}' AND requested_at < '{end_str}' "
        "AND destination_filter != '' "
        "FORMAT JSONEachRow"
    )


def aggregate(
    logs: list[dict],
    baseline_logs: list[dict],
    *,
    window_start: datetime,
    window_end: datetime,
    now: datetime,
) -> SignalDemandState:
    dest_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    horizons: list[int] = []

    for row in logs:
        dest = row.get("destination_filter") or ""
        if dest:
            dest_counts[dest] = dest_counts.get(dest, 0) + 1
        sig_type = row.get("signal_type_filter") or ""
        if sig_type:
            type_counts[sig_type] = type_counts.get(sig_type, 0) + 1
        horizon = row.get("time_horizon_hours_filter")
        if horizon is not None:
            try:
                horizons.append(int(horizon))
            except (TypeError, ValueError):
                pass

    queries_by_destination = sorted(
        [DestinationQueryCount(destination=k, count=v) for k, v in dest_counts.items()],
        key=lambda x: x.count,
        reverse=True,
    )
    queries_by_signal_type = sorted(
        [SignalTypeQueryCount(signal_type=k, count=v) for k, v in type_counts.items()],
        key=lambda x: x.count,
        reverse=True,
    )
    top_destinations = [d.destination for d in queries_by_destination[:5]]
    avg_horizon = sum(horizons) / len(horizons) if horizons else None

    # Baseline for surge detection: counts per destination over the last 24h.
    baseline_dest_counts: dict[str, int] = {}
    for row in baseline_logs:
        dest = row.get("destination_filter") or ""
        if dest:
            baseline_dest_counts[dest] = baseline_dest_counts.get(dest, 0) + 1

    window_hours = max(
        (window_end - window_start).total_seconds() / 3600, 1
    )
    baseline_hours = 24

    demand_surge_destinations: list[str] = []
    for dest, count in dest_counts.items():
        if count < MIN_BUCKET_SAMPLES:
            continue
        baseline_count = baseline_dest_counts.get(dest, 0)
        if baseline_count == 0:
            demand_surge_destinations.append(dest)
            continue
        # Normalise to per-hour rates before comparing.
        observed_rate = count / window_hours
        baseline_rate = baseline_count / baseline_hours
        if baseline_rate > 0 and observed_rate / baseline_rate >= SURGE_MULTIPLIER:
            demand_surge_destinations.append(dest)

    # Urgency trend: compare avg horizon in this window to 24h baseline.
    urgency_trend = "stable"
    if avg_horizon is not None and baseline_logs:
        baseline_horizons = []
        for row in baseline_logs:
            h = row.get("time_horizon_hours_filter")
            if h is not None:
                try:
                    baseline_horizons.append(int(h))
                except (TypeError, ValueError):
                    pass
        if baseline_horizons:
            baseline_avg = sum(baseline_horizons) / len(baseline_horizons)
            if avg_horizon < baseline_avg * 0.8:
                urgency_trend = "shrinking"
            elif avg_horizon > baseline_avg * 1.2:
                urgency_trend = "expanding"

    return SignalDemandState(
        id=f"demand_{uuid4().hex[:12]}",
        window_start=window_start,
        window_end=window_end,
        total_queries=len(logs),
        queries_by_destination=queries_by_destination,
        queries_by_signal_type=queries_by_signal_type,
        avg_requested_time_horizon_hours=avg_horizon,
        urgency_trend=urgency_trend,
        top_destinations=top_destinations,
        demand_surge_destinations=demand_surge_destinations,
        created_at=now,
    )


def run(
    *,
    window_minutes: int = 15,
    dry_run: bool = False,
    now: datetime | None = None,
) -> SignalDemandState | None:
    from jobs.compute_signal_utility_scores import ClickHouseReadClient  # lazy to avoid UTC

    settings = MapsRunnerSettings.from_env()
    ts = now or datetime.now(timezone.utc).replace(tzinfo=None)
    window_end = ts
    window_start = ts - timedelta(minutes=window_minutes)

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

    logs = _fetch_logs(reader, window_start=window_start, window_end=window_end)
    if not logs:
        return None

    baseline_logs = _fetch_baseline_logs(reader, window_end=window_end)
    state = aggregate(logs, baseline_logs, window_start=window_start, window_end=window_end, now=ts)
    writer.insert_signal_demand_state(state)
    return state


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aggregate query access logs into SignalDemandState.")
    parser.add_argument("--window-minutes", type=int, default=15)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    state = run(window_minutes=args.window_minutes, dry_run=args.dry_run)
    if state is None:
        print(json.dumps({"status": "no_logs"}))
    else:
        print(json.dumps({
            "total_queries": state.total_queries,
            "urgency_trend": state.urgency_trend,
            "demand_surge_destinations": state.demand_surge_destinations,
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
