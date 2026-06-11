from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from typing import Sequence

from api.normalizers import normalize_navigation_signal_row
from clients.clickhouse_client import ClickHouseClient
from jobs.compute_signal_utility_scores import ClickHouseReadClient
from schemas.flow_graph import FlowEdge, FlowGraphSnapshot
from schemas.shared_enums import EdgeStatus, SignalStrength, RiskLevel
from services.flow_graph_assembler import assemble
from settings import MapsRunnerSettings


def _parse_datetime(value: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=None)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {value!r}")


def _list_recent_signals(reader: ClickHouseReadClient, *, lookback_hours: int, now: datetime) -> list:
    cutoff = (now - timedelta(hours=lookback_hours)).strftime("%Y-%m-%d %H:%M:%S")
    rows = reader.select(
        f"SELECT * FROM NavigationSignals WHERE created_at >= '{cutoff}' "
        "ORDER BY created_at DESC LIMIT 500 FORMAT JSONEachRow"
    )
    return [normalize_navigation_signal_row(row) for row in rows]


def _get_latest_snapshot_id(reader: ClickHouseReadClient) -> str | None:
    rows = reader.select(
        "SELECT id FROM FlowGraphSnapshots ORDER BY created_at DESC LIMIT 1 FORMAT JSONEachRow"
    )
    return rows[0]["id"] if rows else None


def _list_prev_edges(reader: ClickHouseReadClient, snapshot_id: str) -> list[FlowEdge]:
    rows = reader.select(
        f"SELECT * FROM FlowGraphEdges WHERE snapshot_id = '{snapshot_id}' "
        "FORMAT JSONEachRow"
    )
    return [_normalize_edge_row(row) for row in rows]


def _normalize_edge_row(row: dict) -> FlowEdge:
    return FlowEdge(
        id=row.get("id") or None,
        snapshot_id=row["snapshot_id"],
        origin=row["origin"],
        destination=row["destination"],
        strength=SignalStrength(row["strength"]),
        confidence=float(row["confidence"]),
        hazard_level=RiskLevel(row["hazard_level"]),
        source_signal_ids=list(row.get("source_signal_ids") or []),
        edge_status=EdgeStatus(row["edge_status"]),
        created_at=_parse_datetime(row["created_at"]),
    )


def run(*, lookback_hours: int = 48, now: datetime | None = None) -> tuple[FlowGraphSnapshot, list[FlowEdge]]:
    settings = MapsRunnerSettings.from_env()
    ts = now or datetime.now(UTC).replace(tzinfo=None)

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
    )

    signals = _list_recent_signals(reader, lookback_hours=lookback_hours, now=ts)

    prev_snapshot_id = _get_latest_snapshot_id(reader)
    prev_edges = _list_prev_edges(reader, prev_snapshot_id) if prev_snapshot_id else []

    snapshot, edges = assemble(signals, prev_edges=prev_edges, now=ts)

    writer.insert_flow_graph_snapshot(snapshot)
    if edges:
        writer.insert_flow_graph_edges(edges)

    return snapshot, edges


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Assemble and persist a FlowGraph snapshot.")
    parser.add_argument("--lookback-hours", type=int, default=48)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    snapshot, edges = run(lookback_hours=args.lookback_hours)
    active = [e for e in edges if e.edge_status.value != "closed"]
    print(json.dumps({
        "snapshot_id": snapshot.id,
        "signal_count": snapshot.signal_count,
        "node_count": snapshot.node_count,
        "edge_count": snapshot.edge_count,
        "total_edges_written": len(edges),
        "new": sum(1 for e in edges if e.edge_status.value == "new"),
        "strengthening": sum(1 for e in edges if e.edge_status.value == "strengthening"),
        "weakening": sum(1 for e in edges if e.edge_status.value == "weakening"),
        "closed": sum(1 for e in edges if e.edge_status.value == "closed"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
