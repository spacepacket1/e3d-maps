from __future__ import annotations

import io
import json

from agents.adapter_manager import AdapterManager
from agents.runner import MapsRunner, MapsRuntimeSettings, MapsRunnerSettings, QueueQuestion
from clients.clickhouse_client import ClickHouseClient
from clients.e3d_api_client import E3DAPIClient
from clients.qwen_client import QwenClient


class StubQwenClient(QwenClient):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(request_executor=lambda request, timeout: b"")
        self._responses = list(responses)

    def generate(self, **kwargs) -> str:
        return self._responses.pop(0)


class StubE3DClient(E3DAPIClient):
    def __init__(self, context: dict[str, object]) -> None:
        super().__init__(request_executor=lambda request, timeout: b"")
        self.context = context

    def get_market_context(self, **kwargs) -> dict[str, object]:
        return dict(self.context)


def test_load_question_queue_supports_json_and_yaml(tmp_path):
    json_path = tmp_path / "queue.json"
    yaml_path = tmp_path / "queue.yaml"
    payload = [
        {
            "agent": "capital_migration_agent",
            "question": "Where is capital likely moving over the next 24 hours?",
            "time_horizon_hours": 24,
            "enabled": True,
        }
    ]
    json_path.write_text(json.dumps(payload), encoding="utf-8")
    yaml_path.write_text(
        """
- agent: congestion_agent
  question: Where is congestion forming right now?
  time_horizon_hours: 6
  enabled: true
""".strip(),
        encoding="utf-8",
    )

    runner = MapsRunner(
        runtime_settings=MapsRuntimeSettings(),
        runner_settings=MapsRunnerSettings(),
    )

    json_queue = runner.load_question_queue(str(json_path))
    yaml_queue = runner.load_question_queue(str(yaml_path))

    assert json_queue == [
        QueueQuestion(
            agent="capital_migration_agent",
            question="Where is capital likely moving over the next 24 hours?",
            time_horizon_hours=24,
            enabled=True,
        )
    ]
    assert yaml_queue == [
        QueueQuestion(
            agent="congestion_agent",
            question="Where is congestion forming right now?",
            time_horizon_hours=6,
            enabled=True,
        )
    ]


def test_runner_skips_disabled_questions_and_does_not_write_invalid_outputs():
    qwen_client = StubQwenClient(
        [
            json.dumps(
                {
                    "signal_type": "capital_migration",
                    "question": "Where is capital likely moving over the next 24 hours?",
                    "answer": "Capital appears to be moving toward ETH DeFi.",
                    "origin": "stablecoins",
                    "destination": "ETH_DEFI",
                    "time_horizon_hours": 24,
                    "confidence": 0.7,
                    "risk_level": "medium",
                    "supporting_story_ids": ["story_123"],
                    "created_by_agent": "capital_migration_agent",
                    "model": "qwen",
                    "adapter": "base-v0",
                    "schema_version": "1.0",
                    "outcome_status": "pending",
                    "created_at": "2026-06-08T00:00:00Z",
                }
            ),
            '{"signal_type": "congestion_formation"}',
        ]
    )
    e3d_client = StubE3DClient(
        {
            "recent_stories": [{"id": "story_123", "summary": "signal"}],
            "recent_theses": [],
            "token_activity": [{"id": "token_1", "summary": "stablecoin inflow"}],
            "exchange_flows": [{"id": "flow_1", "summary": "exchange outflow"}],
            "wallet_activity": [{"id": "wallet_1", "summary": "wallet move"}],
            "prior_signals": [],
            "market_state": {"label": "risk_on"},
        }
    )
    output = io.StringIO()
    clickhouse_client = ClickHouseClient(dry_run=True, output=output)
    runner = MapsRunner(
        runtime_settings=MapsRuntimeSettings(),
        runner_settings=MapsRunnerSettings(),
        qwen_client=qwen_client,
        e3d_client=e3d_client,
        clickhouse_client=clickhouse_client,
        adapter_manager=AdapterManager(adapter_name="base-v0"),
    )

    result = runner._run_cycle(
        queue=[
            QueueQuestion(
                agent="capital_migration_agent",
                question="Where is capital likely moving over the next 24 hours?",
                time_horizon_hours=24,
                enabled=True,
            ),
            QueueQuestion(
                agent="destination_prediction_agent",
                question="Which destinations are gaining probability?",
                time_horizon_hours=24,
                enabled=False,
            ),
            QueueQuestion(
                agent="congestion_agent",
                question="Where is congestion forming right now?",
                time_horizon_hours=6,
                enabled=True,
            ),
        ],
        dry_run=True,
    )

    assert result.asked_questions == 2
    assert result.successful_questions == 1
    assert result.skipped_questions == 1
    assert result.invalid_questions == 1
    assert result.written_navigation_signals == 1
    assert result.written_route_predictions == 0
    assert '"table": "NavigationSignals"' in output.getvalue()


def test_runner_once_dry_run_completes_with_sample_fallbacks():
    runner = MapsRunner(
        runtime_settings=MapsRuntimeSettings(),
        runner_settings=MapsRunnerSettings(
            use_sample_context=True,
            use_sample_responses=True,
        ),
        clickhouse_client=ClickHouseClient(dry_run=True, output=io.StringIO()),
        adapter_manager=AdapterManager(adapter_name="base-v0"),
    )

    result = runner.run_once(dry_run=True)

    assert result.asked_questions == 30
    assert result.skipped_questions == 0
    assert result.invalid_questions == 0
    assert result.written_navigation_signals == 30
