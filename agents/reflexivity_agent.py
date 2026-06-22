from __future__ import annotations

from typing import Any, Mapping

from agents.base_agent import BaseAgent
from clients.qwen_client import QwenClient


class ReflexivityAgent(BaseAgent):
    """Emits map_induced_congestion NavigationSignals when consumer_exposure
    data indicates that Maps consumers are crowding a route.

    The detection trigger is deterministic (see jobs/detect_reflexivity.py).
    This agent adds a human-readable explanation of the crowding pattern and
    derives appropriate confidence and risk_level values.
    """

    def __init__(
        self,
        *,
        qwen_client: QwenClient,
        model_name: str | None = None,
        adapter_name: str = "base-v0",
        adapter_path: str | None = None,
    ) -> None:
        super().__init__(
            agent_name="reflexivity_agent",
            question_template=(
                "Is this capital route elevated-risk because Maps consumers "
                "are crowding it, and what should downstream agents know?"
            ),
            system_prompt=self.load_prompt("prompts/maps_system_prompt.md"),
            agent_prompt=self.load_prompt("prompts/reflexivity_agent.md"),
            qwen_client=qwen_client,
            signal_type="map_induced_congestion",
            model_name=model_name,
            adapter_name=adapter_name,
            adapter_path=adapter_path,
        )

    def build_context(self, context: Mapping[str, Any]) -> dict[str, Any]:
        keys = (
            "crowded_destination",
            "crowded_origin",
            "consumer_exposure_count",
            "exposure_window_hours",
            "high_exposure_signals",
            "time_horizon_hours",
        )
        return {key: context[key] for key in keys if key in context}
