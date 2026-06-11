from __future__ import annotations

from typing import Any, Mapping

from agents.base_agent import BaseAgent
from clients.qwen_client import QwenClient


class AgentSwarmFormationAgent(BaseAgent):
    def __init__(
        self,
        *,
        qwen_client: QwenClient,
        model_name: str | None = None,
        adapter_name: str = "base-v0",
        adapter_path: str | None = None,
    ) -> None:
        super().__init__(
            agent_name="agent_swarm_formation_agent",
            question_template="Are agent swarms forming around a common destination?",
            system_prompt=self.load_prompt("prompts/maps_system_prompt.md"),
            agent_prompt=self.load_prompt("prompts/agent_swarm_formation_agent.md"),
            qwen_client=qwen_client,
            signal_type="agent_swarm_formation",
            model_name=model_name,
            adapter_name=adapter_name,
            adapter_path=adapter_path,
        )

    def build_context(self, context: Mapping[str, Any]) -> dict[str, Any]:
        keys = (
            "recent_stories",
            "prior_signals",
            "wallet_cluster_activity",
            "market_state",
            "time_horizon_hours",
        )
        return {key: context[key] for key in keys if key in context}
