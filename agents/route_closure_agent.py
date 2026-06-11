from __future__ import annotations

from typing import Any, Mapping

from agents.base_agent import BaseAgent
from clients.qwen_client import QwenClient


class RouteClosureAgent(BaseAgent):
    def __init__(
        self,
        *,
        qwen_client: QwenClient,
        model_name: str | None = None,
        adapter_name: str = "base-v0",
        adapter_path: str | None = None,
    ) -> None:
        super().__init__(
            agent_name="route_closure_agent",
            question_template="Which capital routes are closing or becoming unavailable over the next {time_horizon_hours} hours?",
            system_prompt=self.load_prompt("prompts/maps_system_prompt.md"),
            agent_prompt=self.load_prompt("prompts/route_closure_agent.md"),
            qwen_client=qwen_client,
            signal_type="route_closure",
            model_name=model_name,
            adapter_name=adapter_name,
            adapter_path=adapter_path,
        )

    def build_context(self, context: Mapping[str, Any]) -> dict[str, Any]:
        keys = (
            "recent_stories",
            "recent_theses",
            "exchange_flows",
            "wallet_cluster_activity",
            "market_state",
            "time_horizon_hours",
        )
        return {key: context[key] for key in keys if key in context}
