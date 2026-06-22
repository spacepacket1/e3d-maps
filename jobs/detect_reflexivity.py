"""Loop 2: Reflexivity Detection job.

Scans NavigationSignals for high consumer_exposure on the same destination and
invokes the ReflexivityAgent to emit a map_induced_congestion warning signal.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Sequence

from clients.clickhouse_client import ClickHouseClient
from clients.qwen_client import QwenClient
from settings import MapsRunnerSettings

EXPOSURE_THRESHOLD: int = int(os.environ.get("MAPS_REFLEXIVITY_EXPOSURE_THRESHOLD", "5"))
LOOKBACK_HOURS: int = int(os.environ.get("MAPS_REFLEXIVITY_LOOKBACK_HOURS", "24"))


class _DryRunFallbackQwenClient(QwenClient):
    def generate(self, *, prompt: str, **_kwargs: object) -> str:
        return "{}"


def _fetch_high_exposure_signals(
    reader: "Any",
    *,
    threshold: int,
    lookback_hours: int,
    now: datetime,
) -> list[dict]:
    cutoff = (now - timedelta(hours=lookback_hours)).strftime("%Y-%m-%d %H:%M:%S")
    return reader.select(
        f"SELECT id, signal_type, destination, origin, consumer_exposure, answer "
        f"FROM NavigationSignals "
        f"WHERE consumer_exposure >= {threshold} AND created_at >= '{cutoff}' "
        f"ORDER BY consumer_exposure DESC "
        f"FORMAT JSONEachRow"
    )


def _group_by_destination(signals: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for sig in signals:
        dest = sig.get("destination") or ""
        if not dest:
            continue
        groups.setdefault(dest, []).append(sig)
    return groups


def run(
    *,
    dry_run: bool = False,
    qwen_client: QwenClient | None = None,
    now: datetime | None = None,
) -> int:
    from jobs.compute_signal_utility_scores import ClickHouseReadClient  # lazy to avoid UTC import
    from agents.reflexivity_agent import ReflexivityAgent
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

    client = qwen_client or (
        _DryRunFallbackQwenClient() if dry_run else QwenClient.from_env()
    )
    agent = ReflexivityAgent(qwen_client=client)

    signals = _fetch_high_exposure_signals(
        reader,
        threshold=EXPOSURE_THRESHOLD,
        lookback_hours=LOOKBACK_HOURS,
        now=ts,
    )
    if not signals:
        return 0

    groups = _group_by_destination(signals)
    emitted = 0

    for dest, dest_signals in groups.items():
        total_exposure = sum(int(s.get("consumer_exposure") or 0) for s in dest_signals)
        if total_exposure < EXPOSURE_THRESHOLD:
            continue

        origin = dest_signals[0].get("origin") or ""
        context = {
            "crowded_destination": dest,
            "crowded_origin": origin,
            "consumer_exposure_count": total_exposure,
            "exposure_window_hours": LOOKBACK_HOURS,
            "high_exposure_signals": dest_signals[:10],
            "time_horizon_hours": 6,
        }
        result = agent.run(context)
        if result and result.navigation_signal:
            writer.insert_navigation_signal(result.navigation_signal)
            emitted += 1

    return emitted


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Detect reflexivity and emit congestion signals.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    count = run(dry_run=args.dry_run)
    print(f"Emitted {count} map_induced_congestion signal(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
