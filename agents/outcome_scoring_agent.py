from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from pydantic import ValidationError

from agents.base_agent import AgentParseError, AgentValidationError
from clients.qwen_client import QwenClient
from schemas.navigation_signal import NavigationSignal
from schemas.prediction_outcome import PredictionOutcome


class OutcomeScoringAgent:
    """Scores whether a prior NavigationSignal prediction came true.

    Receives a NavigationSignal and the post-hoc evidence generated within
    its evaluation window, then returns a PredictionOutcome.

    This is the LLM-based counterpart to the heuristic rubric in
    jobs/score_pending_predictions.py. Both approaches are valid;
    this one uses Qwen reasoning over the raw evidence.
    """

    def __init__(
        self,
        *,
        qwen_client: QwenClient,
        model_name: str | None = None,
        adapter_name: str = "base-v0",
        adapter_path: str | None = None,
    ) -> None:
        self.qwen_client = qwen_client
        self.model_name = model_name or qwen_client.default_model
        self.adapter_name = adapter_name
        self.adapter_path = adapter_path
        self.system_prompt = self._load_prompt("prompts/maps_system_prompt.md")
        self.agent_prompt = self._load_prompt("prompts/outcome_scoring_agent.md")

    @staticmethod
    def _load_prompt(relative_path: str) -> str:
        prompt_path = Path(__file__).resolve().parent.parent / relative_path
        return prompt_path.read_text(encoding="utf-8").strip()

    def score(
        self,
        *,
        signal: NavigationSignal,
        evidence_context: Mapping[str, Any],
    ) -> PredictionOutcome:
        prompt = self._build_prompt(signal=signal, evidence_context=evidence_context)
        raw = self.qwen_client.generate(
            prompt=prompt,
            system_prompt=self.system_prompt,
            model=self.model_name,
            adapter_name=self.adapter_name,
            adapter_path=self.adapter_path,
        )
        return self._parse_outcome(raw, signal=signal)

    def _build_prompt(
        self,
        *,
        signal: NavigationSignal,
        evidence_context: Mapping[str, Any],
    ) -> str:
        signal_json = json.dumps(
            signal.model_dump(mode="json"), indent=2, sort_keys=True, default=str
        )
        context_json = json.dumps(
            dict(evidence_context), indent=2, sort_keys=True, default=str
        )
        return (
            f"{self.agent_prompt}\n\n"
            f"Prior NavigationSignal:\n{signal_json}\n\n"
            f"Post-Hoc Evidence:\n{context_json}\n"
        )

    def _parse_outcome(self, raw: str, *, signal: NavigationSignal) -> PredictionOutcome:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AgentParseError(
                f"outcome_scoring_agent returned invalid JSON: {exc.msg}"
            ) from exc

        if not isinstance(parsed, Mapping):
            raise AgentValidationError(
                "outcome_scoring_agent must return a JSON object."
            )

        now = datetime.now(timezone.utc)
        normalized = dict(parsed)
        normalized.setdefault("navigation_signal_id", signal.id or "")
        normalized.setdefault("evaluation_window_hours", signal.time_horizon_hours)
        normalized.setdefault("created_by_agent", "outcome_scoring_agent")
        if not normalized.get("created_at"):
            normalized["created_at"] = now.isoformat()

        try:
            return PredictionOutcome.model_validate(normalized)
        except ValidationError as exc:
            raise AgentValidationError(
                "outcome_scoring_agent returned an invalid PredictionOutcome."
            ) from exc
