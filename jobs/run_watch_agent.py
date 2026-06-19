from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Sequence

from agents.watch_agent import WatchAgent
from agents.watch_draft_generator import WatchDraftGenerator
from clients.clickhouse_client import ClickHouseClient
from clients.qwen_client import QwenClient, QwenClientError
from clients.watch_feed_client import WatchFeedClient
from schemas.watch_draft import WatchDraft
from schemas.watch_prediction import WatchPrediction
from settings import MapsRunnerSettings, MapsRuntimeSettings

DEFAULT_CANDIDATE_CAP = 20


class _DryRunFallbackQwenClient(QwenClient):
    """Forces the deterministic fallback path so dry runs never hit the network.

    Mirrors jobs/generate_maps_news._DryRunFallbackQwenClient.
    """

    def __init__(self) -> None:
        super().__init__(request_executor=lambda request, timeout: b"")

    def generate(self, **kwargs) -> str:
        raise QwenClientError("dry-run fallback client forces deterministic watch fallback")


@dataclass
class WatchRunResult:
    candidates: int = 0
    predictions: list[WatchPrediction] = field(default_factory=list)
    drafts: list[WatchDraft] = field(default_factory=list)
    predictions_written: int = 0
    drafts_written: int = 0
    used_fallback_predictions: int = 0
    used_fallback_drafts: int = 0
    skipped: int = 0


def run(
    *,
    dry_run: bool = False,
    min_event_score: int | None = None,
    candidate_cap: int = DEFAULT_CANDIDATE_CAP,
    since: str | None = None,
    now: datetime | None = None,
    feed_client: WatchFeedClient | None = None,
    qwen_client: QwenClient | None = None,
    writer: ClickHouseClient | None = None,
) -> WatchRunResult:
    runner_settings = MapsRunnerSettings.from_env()
    runtime_settings = MapsRuntimeSettings.from_env()
    min_score = runner_settings.min_event_score if min_event_score is None else min_event_score
    cap = max(0, candidate_cap)

    feed = feed_client or WatchFeedClient(
        base_url=runner_settings.maps_public_api_base,
        api_key=runner_settings.e3d_api_key,
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

    client = qwen_client
    if client is None:
        client = (
            _DryRunFallbackQwenClient()
            if dry_run
            else QwenClient(
                base_url=runtime_settings.qwen_base_url,
                completions_path=runtime_settings.qwen_completions_path,
                default_model=runtime_settings.qwen_model,
                api_key=runtime_settings.qwen_api_key,
                timeout=runtime_settings.qwen_timeout,
            )
        )

    agent = WatchAgent(
        qwen_client=client,
        model_name=runtime_settings.qwen_model,
        adapter_name=runtime_settings.maps_adapter_name,
        adapter_path=runtime_settings.maps_adapter_path,
    )
    draft_generator = WatchDraftGenerator(
        qwen_client=client,
        feed_client=feed,
        model_name=runtime_settings.qwen_model,
        adapter_name=runtime_settings.maps_adapter_name,
        adapter_path=runtime_settings.maps_adapter_path,
    )

    notable = feed.get_notable(min_score=min_score, since=since, limit=cap)

    result = WatchRunResult(candidates=len(notable))
    seen_keys: set[str] = set()
    for signal in notable[:cap]:
        prediction_result = agent.predict(signal, now=now)
        prediction = prediction_result.prediction
        if prediction is None:
            result.skipped += 1
            continue
        if prediction.idempotency_key in seen_keys:
            continue
        seen_keys.add(prediction.idempotency_key)
        if prediction_result.used_fallback:
            result.used_fallback_predictions += 1

        draft_result = draft_generator.generate(prediction, now=now)
        if draft_result.used_fallback:
            result.used_fallback_drafts += 1

        result.predictions.append(prediction)
        result.drafts.append(draft_result.draft)

    if result.predictions:
        result.predictions_written = clickhouse_writer.insert_watch_predictions(result.predictions)
    if result.drafts:
        result.drafts_written = clickhouse_writer.insert_watch_drafts(result.drafts)
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the E3D Maps Watch Agent.")
    parser.add_argument("--min-event-score", type=int, default=None)
    parser.add_argument("--candidate-cap", type=int, default=DEFAULT_CANDIDATE_CAP)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = run(
        dry_run=args.dry_run,
        min_event_score=args.min_event_score,
        candidate_cap=args.candidate_cap,
    )
    summary: dict[str, Any] = {
        "candidates": result.candidates,
        "predictions_written": result.predictions_written,
        "drafts_written": result.drafts_written,
        "used_fallback_predictions": result.used_fallback_predictions,
        "used_fallback_drafts": result.used_fallback_drafts,
        "skipped": result.skipped,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
