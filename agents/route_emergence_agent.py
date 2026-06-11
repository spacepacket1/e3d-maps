from __future__ import annotations

from typing import Any, Mapping

from agents.base_agent import BaseAgent
from clients.qwen_client import QwenClient


class RouteEmergenceAgent(BaseAgent):
    def __init__(
        self,
        *,
        qwen_client: QwenClient,
        model_name: str | None = None,
        adapter_name: str = "base-v0",
        adapter_path: str | None = None,
    ) -> None:
        super().__init__(
            agent_name="route_emergence_agent",
            question_template="Which new capital routes are opening over the next {time_horizon_hours} hours?",
            system_prompt=self.load_prompt("prompts/maps_system_prompt.md"),
            agent_prompt=self.load_prompt("prompts/route_emergence_agent.md"),
            qwen_client=qwen_client,
            signal_type="route_emergence",
            model_name=model_name,
            adapter_name=adapter_name,
            adapter_path=adapter_path,
        )

    def build_context(self, context: Mapping[str, Any]) -> dict[str, Any]:
        keys = (
            "recent_stories",
            "recent_theses",
            "stablecoin_activity",
            "exchange_flows",
            "market_state",
            "time_horizon_hours",
        )
        return {key: context[key] for key in keys if key in context}
