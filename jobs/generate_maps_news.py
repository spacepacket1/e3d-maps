from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from typing import Sequence

from agents.adapter_manager import AdapterManager
from agents.maps_news_agent import MapsNewsAgent, MapsNewsAgentResult
from clients.clickhouse_client import ClickHouseClient
from clients.qwen_client import QwenClient, QwenClientError
from jobs.compute_signal_utility_scores import ClickHouseReadClient
from schemas.navigation_signal import NavigationSignal
from settings import MapsRunnerSettings, MapsRuntimeSettings


class _DryRunFallbackQwenClient(QwenClient):
    def __init__(self) -> None:
        super().__init__(request_executor=lambda request, timeout: b"")

    def generate(self, **kwargs) -> str:
        raise QwenClientError("dry-run fallback client forces deterministic Maps News fallback")


def _list_recent_strongest_signals(
    reader: ClickHouseReadClient,
    *,
    lookback_hours: int,
    limit: int,
    now: datetime,
) -> list[NavigationSignal]:
    cutoff = (now - timedelta(hours=lookback_hours)).strftime("%Y-%m-%d %H:%M:%S")
    rows = reader.select(
        f"SELECT * FROM NavigationSignals WHERE created_at >= '{cutoff}' "
        "ORDER BY confidence DESC, created_at DESC "
        f"LIMIT {max(0, limit)} FORMAT JSONEachRow"
    )
    from api.normalizers import normalize_navigation_signal_row

    return [normalize_navigation_signal_row(row) for row in rows]


def run(
    *,
    lookback_hours: int = 12,
    signal_limit: int = 50,
    dry_run: bool = False,
    now: datetime | None = None,
    reader: ClickHouseReadClient | None = None,
    writer: ClickHouseClient | None = None,
    qwen_client: QwenClient | None = None,
) -> MapsNewsAgentResult:
    runtime_settings = MapsRuntimeSettings.from_env()
    runner_settings = MapsRunnerSettings.from_env()
    ts = now or datetime.now(UTC).replace(tzinfo=None)

    clickhouse_reader = reader or ClickHouseReadClient(
        host=runner_settings.clickhouse_host,
        port=runner_settings.clickhouse_port,
        database=runner_settings.clickhouse_database,
        username=runner_settings.clickhouse_username,
        password=runner_settings.clickhouse_password,
        secure=runner_settings.clickhouse_secure,
        timeout=runner_settings.clickhouse_timeout,
    )
    clickhouse_writer = writer or ClickHouseClient(
        host=runner_settings.clickhouse_host,
        port=runner_settings.clickhouse_port,
        database=runner_settings.clickhouse_database,
        username=runner_settings.clickhouse_username,
        password=runner_settings.clickhouse_password,
        secure=runner_settings.clickhouse_secure,
        timeout=runner_settings.clickhouse_timeout,
        dry_run=dry_run,
    )

    traffic_state = clickhouse_reader.get_latest_traffic_state()
    cross_chain_state = clickhouse_reader.get_latest_cross_chain_activity_state()
    previous_brief = clickhouse_reader.get_latest_maps_news_brief()
    recent_signals = _list_recent_strongest_signals(
        clickhouse_reader,
        lookback_hours=lookback_hours,
        limit=signal_limit,
        now=ts,
    )

    adapter_manager = AdapterManager.from_settings(runtime_settings)
    adapter_state = adapter_manager.load()
    try:
        client = qwen_client
        if client is None:
            if dry_run:
                client = _DryRunFallbackQwenClient()
            else:
                client = QwenClient(
                    base_url=runtime_settings.qwen_base_url,
                    completions_path=runtime_settings.qwen_completions_path,
                    default_model=runtime_settings.qwen_model,
                    api_key=runtime_settings.qwen_api_key,
                    timeout=runtime_settings.qwen_timeout,
                )

        agent = MapsNewsAgent(
            qwen_client=client,
            model_name=runtime_settings.qwen_model,
            adapter_name=adapter_state.name,
            adapter_path=adapter_state.path,
        )
        result = agent.run(
            {
                "traffic_state": traffic_state,
                "cross_chain_activity_state": cross_chain_state,
                "previous_brief": previous_brief,
                "recent_signals": recent_signals,
            }
        )
        clickhouse_writer.insert_maps_news_brief(result.brief)
        return result
    finally:
        adapter_manager.unload()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate and persist a MapsNewsBrief.")
    parser.add_argument("--lookback-hours", type=int, default=12)
    parser.add_argument("--signal-limit", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = run(
        lookback_hours=args.lookback_hours,
        signal_limit=args.signal_limit,
        dry_run=args.dry_run,
    )
    print(
        json.dumps(
            {
                "headline": result.brief.headline,
                "stance": result.brief.stance,
                "tags": result.brief.tags,
                "supporting_signal_ids": len(result.brief.supporting_signal_ids),
                "used_fallback": result.used_fallback,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
