"""Loop 5: Route Health Reporting job.

For each unique destination/origin seen in recent NavigationSignals, computes a
health_score and invokes RouteHealthAgent to produce a RouteHealthReport.
"""
from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Sequence

from clients.clickhouse_client import ClickHouseClient
from clients.qwen_client import QwenClient
from settings import MapsRunnerSettings, MapsRuntimeSettings

LOOKBACK_HOURS: int = int(os.environ.get("MAPS_ROUTE_HEALTH_LOOKBACK_HOURS", "24"))
MIN_SIGNALS: int = int(os.environ.get("MAPS_ROUTE_HEALTH_MIN_SIGNALS", "3"))
MAX_PROTOCOLS: int = int(os.environ.get("MAPS_ROUTE_HEALTH_MAX_PROTOCOLS", "20"))
HAZARD_SIGNAL_TYPES = frozenset({"route_hazard", "map_induced_congestion"})
CLOSURE_SIGNAL_TYPES = frozenset({"route_closure"})
EMERGENCE_SIGNAL_TYPES = frozenset({"route_emergence"})


class _DryRunFallbackQwenClient(QwenClient):
    def generate(self, *, prompt: str, **_kwargs: object) -> str:
        return '{"traffic_trend":"stable","congestion_level":"low","hazard_level":"low","summary":"Dry-run placeholder."}'


def _fetch_recent_signals(
    reader: "Any",
    *,
    since: datetime,
    now: datetime,
) -> list[dict]:
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    return reader.select(
        f"SELECT id, signal_type, origin, destination, confidence, risk_level "
        f"FROM NavigationSignals "
        f"WHERE created_at >= '{since_str}' AND created_at < '{now_str}' "
        f"FORMAT JSONEachRow"
    )


def _compute_health_score(signals: list[dict]) -> float:
    if not signals:
        return 0.5
    hazard_count = sum(
        1 for s in signals if s.get("signal_type") in HAZARD_SIGNAL_TYPES
    )
    avg_confidence = sum(
        float(s.get("confidence") or 0.5) for s in signals
    ) / len(signals)
    hazard_ratio = hazard_count / len(signals)
    # Health score: avg_confidence penalised by hazard ratio.
    return round(max(0.0, min(1.0, avg_confidence * (1.0 - hazard_ratio))), 4)


def run(
    *,
    dry_run: bool = False,
    qwen_client: QwenClient | None = None,
    now: datetime | None = None,
) -> int:
    from jobs.compute_signal_utility_scores import ClickHouseReadClient  # lazy to avoid UTC import
    from agents.route_health_agent import RouteHealthAgent
    settings = MapsRunnerSettings.from_env()
    runtime_settings = MapsRuntimeSettings.from_env()
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
    client = qwen_client or (
        _DryRunFallbackQwenClient() if dry_run else QwenClient.from_env()
    )
    agent = RouteHealthAgent(
        qwen_client=client,
        model_name=runtime_settings.qwen_model,
        adapter_name=runtime_settings.maps_adapter_name,
        adapter_path=runtime_settings.maps_adapter_path,
    )

    all_signals = _fetch_recent_signals(reader, since=since, now=ts)
    if not all_signals:
        return 0

    # Group signals by destination (the protocol/chain being routed to).
    dest_signals: dict[str, list[dict]] = {}
    for sig in all_signals:
        dest = sig.get("destination") or ""
        if not dest:
            continue
        dest_signals.setdefault(dest, []).append(sig)

    # Sort by signal count descending, cap at MAX_PROTOCOLS.
    sorted_dests = sorted(dest_signals.items(), key=lambda kv: len(kv[1]), reverse=True)
    sorted_dests = sorted_dests[:MAX_PROTOCOLS]

    written = 0
    for dest, signals in sorted_dests:
        if len(signals) < MIN_SIGNALS:
            continue
        health_score = _compute_health_score(signals)
        emergence_count = sum(
            1 for s in signals if s.get("signal_type") in EMERGENCE_SIGNAL_TYPES
        )
        closure_count = sum(
            1 for s in signals if s.get("signal_type") in CLOSURE_SIGNAL_TYPES
        )
        hazard_count = sum(
            1 for s in signals if s.get("signal_type") in HAZARD_SIGNAL_TYPES
        )

        context = {
            "protocol_or_chain": dest,
            "report_scope": "protocol",
            "health_score": health_score,
            "recent_signals": signals[:20],
            "route_emergence_count": emergence_count,
            "route_closure_count": closure_count,
            "hazard_signal_count": hazard_count,
            "total_signal_count": len(signals),
            "time_horizon_hours": LOOKBACK_HOURS,
        }
        result = agent.generate_report(context)
        if result.report:
            writer.insert_route_health_report(result.report)
            written += 1

    return written


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Generate route health reports.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    count = run(dry_run=args.dry_run)
    print(f"Wrote {count} RouteHealthReport(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
