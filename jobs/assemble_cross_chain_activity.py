from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from typing import Sequence

from api.normalizers import normalize_navigation_signal_row
from clients.clickhouse_client import ClickHouseClient
from jobs.compute_signal_utility_scores import ClickHouseReadClient
from schemas.cross_chain_activity_state import CrossChainActivityState
from schemas.navigation_signal import NavigationSignal
from services.cross_chain_activity_assembler import assemble_cross_chain_activity_state
from settings import MapsRunnerSettings


_RELEVANT_SIGNAL_TYPES = (
    "capital_migration",
    "destination_prediction",
    "route_emergence",
    "route_hazard",
    "route_closure",
    "congestion_formation",
)


def _list_recent_relevant_signals(
    reader: ClickHouseReadClient,
    *,
    lookback_hours: int,
    limit: int,
    now: datetime,
) -> list[NavigationSignal]:
    cutoff = (now - timedelta(hours=lookback_hours)).strftime("%Y-%m-%d %H:%M:%S")
    signal_types = ", ".join(f"'{signal_type}'" for signal_type in _RELEVANT_SIGNAL_TYPES)
    rows = reader.select(
        f"SELECT * FROM NavigationSignals WHERE created_at >= '{cutoff}' "
        f"AND signal_type IN ({signal_types}) "
        "ORDER BY created_at DESC "
        f"LIMIT {max(0, limit)} FORMAT JSONEachRow"
    )
    return [normalize_navigation_signal_row(row) for row in rows]


def run(
    *,
    lookback_hours: int = 24,
    signal_limit: int = 200,
    dry_run: bool = False,
    now: datetime | None = None,
    reader: ClickHouseReadClient | None = None,
    writer: ClickHouseClient | None = None,
) -> CrossChainActivityState:
    settings = MapsRunnerSettings.from_env()
    ts = now or datetime.now(UTC).replace(tzinfo=None)

    clickhouse_reader = reader or ClickHouseReadClient(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        database=settings.clickhouse_database,
        username=settings.clickhouse_username,
        password=settings.clickhouse_password,
        secure=settings.clickhouse_secure,
        timeout=settings.clickhouse_timeout,
    )
    clickhouse_writer = writer or ClickHouseClient(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        database=settings.clickhouse_database,
        username=settings.clickhouse_username,
        password=settings.clickhouse_password,
        secure=settings.clickhouse_secure,
        timeout=settings.clickhouse_timeout,
        dry_run=dry_run,
    )

    signals = _list_recent_relevant_signals(
        clickhouse_reader,
        lookback_hours=lookback_hours,
        limit=signal_limit,
        now=ts,
    )
    traffic_state = clickhouse_reader.get_latest_traffic_state()
    state = assemble_cross_chain_activity_state(signals, traffic_state)
    clickhouse_writer.insert_cross_chain_activity_state(state)
    return state


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Assemble and persist a CrossChainActivityState snapshot."
    )
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--signal-limit", type=int, default=200)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    state = run(
        lookback_hours=args.lookback_hours,
        signal_limit=args.signal_limit,
        dry_run=args.dry_run,
    )
    print(
        json.dumps(
            {
                "market_bias": state.market_bias,
                "top_routes": len(state.top_routes),
                "active_hazards": len(state.active_hazards),
                "active_congestion": len(state.active_congestion),
                "top_destinations": len(state.top_destinations),
                "supporting_signal_ids": len(state.supporting_signal_ids),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
