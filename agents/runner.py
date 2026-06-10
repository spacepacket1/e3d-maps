from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from agents import (
    AgentError,
    BaseAgent,
    CapitalMigrationAgent,
    CongestionAgent,
    DestinationPredictionAgent,
    RouteHazardAgent,
)
from agents.adapter_manager import AdapterManager
from clients.clickhouse_client import ClickHouseClient
from clients._base_api_client import E3DAPIClientError
from clients.e3d_api_client import E3DAPIClient
from clients.qwen_client import QwenClient, QwenClientError
from settings import MapsRunnerSettings, MapsRuntimeSettings


class QuestionQueueError(RuntimeError):
    """Raised when the runner question queue config is invalid."""


@dataclass(frozen=True)
class QueueQuestion:
    agent: str
    question: str
    time_horizon_hours: int
    enabled: bool = True


@dataclass(frozen=True)
class RunnerCycleResult:
    asked_questions: int = 0
    successful_questions: int = 0
    skipped_questions: int = 0
    invalid_questions: int = 0
    written_navigation_signals: int = 0
    written_route_predictions: int = 0


class SampleFallbackQwenClient(QwenClient):
    def __init__(
        self,
        *,
        fallback_enabled: bool,
        response_factory: Callable[[str], str],
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.fallback_enabled = fallback_enabled
        self.response_factory = response_factory

    def generate(self, **kwargs) -> str:
        try:
            return super().generate(**kwargs)
        except QwenClientError:
            if not self.fallback_enabled:
                raise
            prompt = kwargs.get("prompt")
            if not isinstance(prompt, str):
                raise
            return self.response_factory(prompt)


class MapsRunner:
    AGENT_FACTORIES: Mapping[str, type[BaseAgent]] = {
        "capital_migration_agent": CapitalMigrationAgent,
        "congestion_agent": CongestionAgent,
        "route_hazard_agent": RouteHazardAgent,
        "destination_prediction_agent": DestinationPredictionAgent,
    }

    def __init__(
        self,
        *,
        runtime_settings: MapsRuntimeSettings,
        runner_settings: MapsRunnerSettings,
        qwen_client: QwenClient | None = None,
        e3d_client: E3DAPIClient | None = None,
        clickhouse_client: ClickHouseClient | None = None,
        adapter_manager: AdapterManager | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.runtime_settings = runtime_settings
        self.runner_settings = runner_settings
        self.qwen_client = qwen_client or SampleFallbackQwenClient(
            base_url=runtime_settings.qwen_base_url,
            completions_path=runtime_settings.qwen_completions_path,
            default_model=runtime_settings.qwen_model,
            api_key=runtime_settings.qwen_api_key,
            timeout=runtime_settings.qwen_timeout,
            fallback_enabled=runner_settings.use_sample_responses,
            response_factory=self._sample_response_for_prompt,
        )
        self.e3d_client = e3d_client or E3DAPIClient(
            base_url=runner_settings.e3d_base_url,
            api_prefix=runner_settings.e3d_api_prefix,
            api_key=runner_settings.e3d_api_key,
        )
        self.clickhouse_client = clickhouse_client or ClickHouseClient(
            host=runner_settings.clickhouse_host,
            port=runner_settings.clickhouse_port,
            database=runner_settings.clickhouse_database,
            username=runner_settings.clickhouse_username,
            password=runner_settings.clickhouse_password,
            secure=runner_settings.clickhouse_secure,
            timeout=runner_settings.clickhouse_timeout,
        )
        self.adapter_manager = adapter_manager or AdapterManager.from_settings(runtime_settings)
        self.sleep_fn = sleep_fn

    def load_question_queue(self, path: str | None = None) -> list[QueueQuestion]:
        queue_path = Path(path or self.runner_settings.question_queue_path or self.default_queue_path())
        raw_items = self._load_queue_file(queue_path)
        questions: list[QueueQuestion] = []

        for index, item in enumerate(raw_items):
            if not isinstance(item, Mapping):
                raise QuestionQueueError(
                    f"Question queue entry {index} in {queue_path} must be an object."
                )
            try:
                questions.append(
                    QueueQuestion(
                        agent=str(item["agent"]),
                        question=str(item["question"]).strip(),
                        time_horizon_hours=int(item["time_horizon_hours"]),
                        enabled=bool(item.get("enabled", True)),
                    )
                )
            except KeyError as exc:
                raise QuestionQueueError(
                    f"Question queue entry {index} in {queue_path} is missing {exc.args[0]!r}."
                ) from exc

        return questions

    def run_once(self, *, dry_run: bool = False) -> RunnerCycleResult:
        queue = self.load_question_queue()
        return self._run_cycle(queue=queue, dry_run=dry_run)

    def run_loop(self, *, dry_run: bool = False) -> None:
        while True:
            self.run_once(dry_run=dry_run)
            self.sleep_fn(self.runner_settings.run_interval_seconds)

    def _run_cycle(
        self,
        *,
        queue: Sequence[QueueQuestion],
        dry_run: bool,
    ) -> RunnerCycleResult:
        adapter_state = self.adapter_manager.load()
        try:
            context = self._load_context(allow_sample_fallback=dry_run or self.runner_settings.use_sample_context)
            clickhouse = self._clickhouse_for_cycle(dry_run=dry_run)
            result = RunnerCycleResult()

            for question in queue:
                if not question.enabled:
                    result = self._replace_result(
                        result,
                        skipped_questions=result.skipped_questions + 1,
                    )
                    continue

                agent_factory = self.AGENT_FACTORIES.get(question.agent)
                if agent_factory is None:
                    result = self._replace_result(
                        result,
                        invalid_questions=result.invalid_questions + 1,
                    )
                    continue

                result = self._replace_result(
                    result,
                    asked_questions=result.asked_questions + 1,
                )
                agent = agent_factory(
                    qwen_client=self.qwen_client,
                    model_name=self.runtime_settings.qwen_model,
                    adapter_name=adapter_state.name,
                    adapter_path=adapter_state.path,
                )

                try:
                    run_result = agent.run(
                        {
                            **context,
                            "question": question.question,
                            "time_horizon_hours": question.time_horizon_hours,
                        }
                    )
                except AgentError:
                    result = self._replace_result(
                        result,
                        invalid_questions=result.invalid_questions + 1,
                    )
                    continue

                if run_result.navigation_signal is None:
                    result = self._replace_result(
                        result,
                        successful_questions=result.successful_questions + 1,
                    )
                    continue

                written_signals = clickhouse.insert_navigation_signal(run_result.navigation_signal)
                written_routes = clickhouse.insert_route_predictions(run_result.route_predictions)
                result = self._replace_result(
                    result,
                    successful_questions=result.successful_questions + 1,
                    written_navigation_signals=result.written_navigation_signals + written_signals,
                    written_route_predictions=result.written_route_predictions + written_routes,
                )

            return result
        finally:
            self.adapter_manager.unload()

    @staticmethod
    def _replace_result(result: RunnerCycleResult, **updates: int) -> RunnerCycleResult:
        return RunnerCycleResult(
            asked_questions=updates.get("asked_questions", result.asked_questions),
            successful_questions=updates.get("successful_questions", result.successful_questions),
            skipped_questions=updates.get("skipped_questions", result.skipped_questions),
            invalid_questions=updates.get("invalid_questions", result.invalid_questions),
            written_navigation_signals=updates.get(
                "written_navigation_signals",
                result.written_navigation_signals,
            ),
            written_route_predictions=updates.get(
                "written_route_predictions",
                result.written_route_predictions,
            ),
        )

    def _load_context(self, *, allow_sample_fallback: bool) -> dict[str, Any]:
        try:
            context = self.e3d_client.get_market_context()
            return {
                "recent_stories": context.get("recent_stories", []),
                "recent_theses": context.get("recent_theses", []),
                "stablecoin_activity": self._coerce_summary_block(context.get("token_activity")),
                "exchange_flows": self._coerce_summary_block(context.get("exchange_flows")),
                "wallet_cluster_activity": self._coerce_summary_block(context.get("wallet_activity")),
                "prior_signals": context.get("prior_signals", []),
                "market_state": context.get("market_state", {}),
            }
        except E3DAPIClientError:
            if not allow_sample_fallback:
                raise
            return self.sample_context()

    def _clickhouse_for_cycle(self, *, dry_run: bool) -> ClickHouseClient:
        if not dry_run:
            return self.clickhouse_client
        return ClickHouseClient(
            host=self.clickhouse_client.host,
            port=self.clickhouse_client.port,
            database=self.clickhouse_client.database,
            username=self.clickhouse_client.username,
            password=self.clickhouse_client.password,
            secure=self.clickhouse_client.secure,
            timeout=self.clickhouse_client.timeout,
            dry_run=True,
            output=self.clickhouse_client.output,
            request_executor=self.clickhouse_client._request_executor,
        )

    @staticmethod
    def default_queue_path() -> Path:
        return Path(__file__).with_name("question_queue.json")

    @staticmethod
    def _load_queue_file(path: Path) -> list[Any]:
        suffix = path.suffix.lower()
        text = path.read_text(encoding="utf-8")

        if suffix == ".json":
            payload = json.loads(text)
        elif suffix in {".yaml", ".yml"}:
            payload = MapsRunner._load_simple_yaml_list(text)
        else:
            raise QuestionQueueError(f"Unsupported question queue format: {path.suffix}")

        if not isinstance(payload, list):
            raise QuestionQueueError(f"Question queue file {path} must contain a top-level array.")
        return payload

    @staticmethod
    def _load_simple_yaml_list(text: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None

        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            if stripped.startswith("- "):
                if current is not None:
                    items.append(current)
                current = {}
                stripped = stripped[2:].strip()
                if stripped:
                    key, value = MapsRunner._split_yaml_key_value(stripped)
                    current[key] = MapsRunner._parse_yaml_scalar(value)
                continue

            if current is None:
                raise QuestionQueueError("YAML question queue must be a top-level list.")

            key, value = MapsRunner._split_yaml_key_value(stripped)
            current[key] = MapsRunner._parse_yaml_scalar(value)

        if current is not None:
            items.append(current)

        return items

    @staticmethod
    def _split_yaml_key_value(text: str) -> tuple[str, str]:
        if ":" not in text:
            raise QuestionQueueError(f"Invalid YAML question queue line: {text!r}")
        key, value = text.split(":", 1)
        return key.strip(), value.strip()

    @staticmethod
    def _parse_yaml_scalar(value: str) -> Any:
        lowered = value.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        if value.isdigit():
            return int(value)
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            return value[1:-1]
        return value

    @staticmethod
    def _coerce_summary_block(value: Any) -> Any:
        if isinstance(value, list):
            if len(value) == 1 and isinstance(value[0], Mapping):
                return dict(value[0])
            return [dict(item) for item in value if isinstance(item, Mapping)]
        if isinstance(value, Mapping):
            return dict(value)
        return {}

    @staticmethod
    def sample_context() -> dict[str, Any]:
        return {
            "recent_stories": [
                {
                    "id": "story_123",
                    "story_type": "stablecoin_activity",
                    "summary": "Stablecoin inflows increased into Ethereum DeFi wallets.",
                    "timestamp": "2026-06-08T00:00:00Z",
                }
            ],
            "recent_theses": [
                {
                    "id": "thesis_789",
                    "summary": "ETH DeFi is regaining traction.",
                    "direction": "bullish",
                    "conviction": "medium",
                }
            ],
            "stablecoin_activity": {"netflow": "positive"},
            "exchange_flows": {"ETH": {"netflow": "outflow"}},
            "wallet_cluster_activity": [{"cluster": "smart_money", "destination": "AAVE"}],
            "prior_signals": [],
            "market_state": {"label": "risk_on", "rationale": "capital rotating into DeFi"},
        }

    @staticmethod
    def _sample_response_for_prompt(prompt: str) -> str:
        if "capital_migration_agent" in prompt or "Where is capital likely moving" in prompt:
            return json.dumps(
                {
                    "navigation_signal": {
                        "signal_type": "capital_migration",
                        "question": "Where is capital likely moving over the next 24 hours?",
                        "answer": "Capital appears to be rotating from stablecoins into ETH DeFi. Recent story and thesis context point toward lending protocols as the likely destination.",
                        "origin": "stablecoins",
                        "destination": "ETH_DEFI",
                        "asset_scope": ["ETH", "AAVE"],
                        "chain_scope": ["ethereum"],
                        "time_horizon_hours": 24,
                        "confidence": 0.72,
                        "risk_level": "medium",
                        "signal_strength": "strong",
                        "market_state": "risk_on",
                        "supporting_story_ids": ["story_123"],
                        "supporting_thesis_ids": ["thesis_789"],
                        "evidence": [
                            {
                                "type": "story",
                                "id": "story_123",
                                "summary": "Stablecoin inflows increased into Ethereum DeFi wallets.",
                            }
                        ],
                        "recommended_action": "monitor_or_increase_eth_defi_exposure",
                    },
                    "route_predictions": [
                        {
                            "route_type": "destination_prediction",
                            "origin": "stablecoins",
                            "destination": "ETH_DEFI",
                            "expected_flow_direction": "inflow",
                            "expected_flow_magnitude": "moderate",
                            "time_horizon_hours": 24,
                            "confidence": 0.69,
                            "hazards": [],
                            "supporting_story_ids": ["story_123"],
                        }
                    ],
                }
            )
        if "congestion_agent" in prompt or "Where is congestion forming" in prompt:
            return json.dumps(
                {
                    "signal_type": "congestion_formation",
                    "question": "Where is congestion forming right now?",
                    "answer": "Crowding is forming around ETH DeFi inflows, especially in lending venues. Evidence is limited but consistent with a near-term traffic buildup.",
                    "origin": "stablecoins",
                    "destination": "ETH_DEFI",
                    "time_horizon_hours": 6,
                    "confidence": 0.56,
                    "risk_level": "medium",
                    "supporting_story_ids": ["story_123"],
                    "evidence": [
                        {
                            "type": "story",
                            "id": "story_123",
                            "summary": "Stablecoin inflows increased into Ethereum DeFi wallets.",
                        }
                    ],
                }
            )
        if "route_hazard_agent" in prompt or "Which capital routes are becoming unsafe?" in prompt:
            return json.dumps(
                {
                    "signal_type": "route_hazard",
                    "question": "Which capital routes are becoming unsafe?",
                    "answer": "No acute closure is visible, but congestion risk is rising on the route into ETH DeFi. The route remains open with moderate hazard.",
                    "origin": "stablecoins",
                    "destination": "ETH_DEFI",
                    "time_horizon_hours": 24,
                    "confidence": 0.51,
                    "risk_level": "medium",
                    "supporting_story_ids": ["story_123"],
                    "evidence": [
                        {
                            "type": "story",
                            "id": "story_123",
                            "summary": "Stablecoin inflows increased into Ethereum DeFi wallets.",
                        }
                    ],
                }
            )
        return json.dumps(
            {
                "navigation_signal": {
                    "signal_type": "destination_prediction",
                    "question": "Which destinations are gaining probability?",
                    "answer": "ETH DeFi is the likeliest destination for near-term capital deployment. The evidence is moderate and primarily flow-driven.",
                    "origin": "stablecoins",
                    "destination": "ETH_DEFI",
                    "asset_scope": ["ETH", "AAVE"],
                    "chain_scope": ["ethereum"],
                    "time_horizon_hours": 24,
                    "confidence": 0.66,
                    "risk_level": "low",
                    "signal_strength": "moderate",
                    "market_state": "risk_on",
                    "supporting_story_ids": ["story_123"],
                    "supporting_thesis_ids": ["thesis_789"],
                    "evidence": [
                        {
                            "type": "story",
                            "id": "story_123",
                            "summary": "Stablecoin inflows increased into Ethereum DeFi wallets.",
                        }
                    ],
                },
                "route_predictions": [
                    {
                        "route_type": "destination_prediction",
                        "origin": "stablecoins",
                        "destination": "ETH_DEFI",
                        "expected_flow_direction": "inflow",
                        "expected_flow_magnitude": "moderate",
                        "time_horizon_hours": 24,
                        "confidence": 0.64,
                        "hazards": [],
                        "supporting_story_ids": ["story_123"],
                    }
                ],
            }
        )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the E3D Maps runner.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="Run a single Maps cycle.")
    mode.add_argument("--loop", action="store_true", help="Run the Maps cycle continuously.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print writes without inserting.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    runtime_settings = MapsRuntimeSettings.from_env()
    runner_settings = MapsRunnerSettings.from_env()

    if args.dry_run:
        runner_settings = MapsRunnerSettings(
            **{
                **runner_settings.__dict__,
                "use_sample_context": True if not runner_settings.use_sample_context else runner_settings.use_sample_context,
                "use_sample_responses": True if not runner_settings.use_sample_responses else runner_settings.use_sample_responses,
            }
        )

    runner = MapsRunner(
        runtime_settings=runtime_settings,
        runner_settings=runner_settings,
    )

    if args.once:
        result = runner.run_once(dry_run=args.dry_run)
        print(json.dumps(result.__dict__, sort_keys=True))
        return 0

    runner.run_loop(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
