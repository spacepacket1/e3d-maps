from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Sequence

from api.normalizers import normalize_navigation_signal_row
from clients.clickhouse_client import ClickHouseClient
from jobs.compute_signal_utility_scores import ClickHouseReadClient
from schemas.shared_enums import MarketState, SignalStrength
from schemas.traffic_state import DominantFlow, TopDestination, TrafficState
from settings import MapsRunnerSettings


_FLOW_SIGNAL_TYPES = frozenset({"capital_migration", "destination_prediction", "capital_conviction"})
_DEST_SIGNAL_TYPES = frozenset({"destination_prediction", "capital_migration", "capital_conviction", "route_emergence"})
_HAZARD_SIGNAL_TYPES = frozenset({"route_hazard", "route_closure"})


def _list_recent_signals(reader: ClickHouseReadClient, *, lookback_hours: int, now: datetime) -> list:
    cutoff = (now - timedelta(hours=lookback_hours)).strftime("%Y-%m-%d %H:%M:%S")
    rows = reader.select(
        f"SELECT * FROM NavigationSignals WHERE created_at >= '{cutoff}' "
        "ORDER BY created_at DESC LIMIT 1000 FORMAT JSONEachRow"
    )
    return [normalize_navigation_signal_row(row) for row in rows]


def _derive_market_state(signals: list) -> MarketState:
    counts: Counter[str] = Counter(
        s.market_state.value for s in signals if s.market_state is not None
    )
    if not counts:
        return MarketState.NEUTRAL
    top = counts.most_common(1)[0][0]
    try:
        return MarketState(top)
    except ValueError:
        return MarketState.NEUTRAL


def _derive_dominant_flows(signals: list, *, top_n: int = 5) -> list[DominantFlow]:
    bucket: dict[tuple[str, str], list[float]] = defaultdict(list)
    for s in signals:
        if s.signal_type in _FLOW_SIGNAL_TYPES and s.origin and s.destination:
            bucket[(s.origin, s.destination)].append(s.confidence)
    scored = sorted(
        bucket.items(),
        key=lambda kv: -(sum(kv[1]) / len(kv[1])),
    )
    result: list[DominantFlow] = []
    for (origin, destination), confs in scored[:top_n]:
        avg = sum(confs) / len(confs)
        if avg >= 0.7:
            strength = SignalStrength.STRONG
        elif avg >= 0.5:
            strength = SignalStrength.MODERATE
        else:
            strength = SignalStrength.WEAK
        result.append(DominantFlow(origin=origin, destination=destination, strength=strength))
    return result


def _derive_top_destinations(signals: list, *, top_n: int = 5) -> list[TopDestination]:
    bucket: dict[str, list[float]] = defaultdict(list)
    for s in signals:
        if s.signal_type in _DEST_SIGNAL_TYPES and s.destination:
            bucket[s.destination].append(s.confidence)
    scored = sorted(
        bucket.items(),
        key=lambda kv: -(sum(kv[1]) / len(kv[1])),
    )
    return [
        TopDestination(destination=dest, confidence=round(sum(confs) / len(confs), 4))
        for dest, confs in scored[:top_n]
    ]


def _derive_congestion_zones(signals: list) -> list[str]:
    best: dict[str, float] = {}
    for s in signals:
        if s.signal_type == "congestion_formation" and s.destination:
            if s.destination not in best or s.confidence > best[s.destination]:
                best[s.destination] = s.confidence
    return [dest for dest, _ in sorted(best.items(), key=lambda kv: -kv[1])]


def _derive_hazard_labels(signals: list) -> list[str]:
    best: dict[str, float] = {}
    for s in signals:
        if s.signal_type in _HAZARD_SIGNAL_TYPES and s.destination:
            label = f"{s.signal_type}: {s.destination}"
            if label not in best or s.confidence > best[label]:
                best[label] = s.confidence
    return [label for label, _ in sorted(best.items(), key=lambda kv: -kv[1])[:10]]


def assemble_traffic_state(signals: list, *, now: datetime) -> TrafficState:
    return TrafficState(
        scope="global",
        market_state=_derive_market_state(signals),
        dominant_flows=_derive_dominant_flows(signals),
        congestion_zones=_derive_congestion_zones(signals),
        hazards=_derive_hazard_labels(signals),
        top_destinations=_derive_top_destinations(signals),
        created_by_agent="traffic_state_assembler",
        created_at=now,
    )


def run(
    *,
    lookback_hours: int = 48,
    dry_run: bool = False,
    now: datetime | None = None,
) -> TrafficState:
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
        dry_run=dry_run,
    )

    signals = _list_recent_signals(reader, lookback_hours=lookback_hours, now=ts)
    state = assemble_traffic_state(signals, now=ts)
    writer.insert_traffic_state(state)
    return state


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Assemble and persist a TrafficState snapshot.")
    parser.add_argument("--lookback-hours", type=int, default=48)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    state = run(lookback_hours=args.lookback_hours, dry_run=args.dry_run)
    print(json.dumps({
        "market_state": state.market_state.value,
        "dominant_flows": len(state.dominant_flows),
        "top_destinations": len(state.top_destinations),
        "congestion_zones": len(state.congestion_zones),
        "hazards": len(state.hazards),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
