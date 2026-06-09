from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from agents.base_agent import AgentParseError, AgentValidationError
from clients.qwen_client import QwenClient


@dataclass(frozen=True)
class ConfidenceAssessment:
    confidence: float
    confidence_explanation: str
    calibration_notes: str


class ConfidenceScoringAgent:
    """Calibrates the confidence value on a NavigationSignal draft.

    Receives a signal draft and the evidence context used to generate it,
    then returns a ConfidenceAssessment with a calibrated confidence score,
    an explanation, and calibration notes.
    """

    CONFIDENCE_FLOOR = 0.30
    CONFIDENCE_CEILING = 0.90

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
        self.agent_prompt = self._load_prompt("prompts/confidence_scoring_agent.md")

    @staticmethod
    def _load_prompt(relative_path: str) -> str:
        prompt_path = Path(__file__).resolve().parent.parent / relative_path
        return prompt_path.read_text(encoding="utf-8").strip()

    def score(
        self,
        *,
        signal_draft: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> ConfidenceAssessment:
        prompt = self._build_prompt(signal_draft=signal_draft, context=context)
        raw = self.qwen_client.generate(
            prompt=prompt,
            system_prompt=self.system_prompt,
            model=self.model_name,
            adapter_name=self.adapter_name,
            adapter_path=self.adapter_path,
        )
        return self._parse_assessment(raw)

    def _build_prompt(
        self,
        *,
        signal_draft: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> str:
        signal_json = json.dumps(dict(signal_draft), indent=2, sort_keys=True, default=str)
        context_json = json.dumps(dict(context), indent=2, sort_keys=True, default=str)
        return (
            f"{self.agent_prompt}\n\n"
            f"Signal Draft:\n{signal_json}\n\n"
            f"Context:\n{context_json}\n"
        )

    def _parse_assessment(self, raw: str) -> ConfidenceAssessment:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AgentParseError(
                f"confidence_scoring_agent returned invalid JSON: {exc.msg}"
            ) from exc

        if not isinstance(parsed, Mapping):
            raise AgentValidationError(
                "confidence_scoring_agent must return a JSON object."
            )

        confidence = parsed.get("confidence")
        if not isinstance(confidence, (int, float)):
            raise AgentValidationError(
                f"confidence_scoring_agent returned non-numeric confidence: {confidence!r}."
            )
        confidence = float(confidence)
        if not (self.CONFIDENCE_FLOOR <= confidence <= self.CONFIDENCE_CEILING):
            raise AgentValidationError(
                f"confidence_scoring_agent confidence {confidence} is outside "
                f"[{self.CONFIDENCE_FLOOR}, {self.CONFIDENCE_CEILING}]."
            )

        return ConfidenceAssessment(
            confidence=confidence,
            confidence_explanation=str(parsed.get("confidence_explanation") or ""),
            calibration_notes=str(parsed.get("calibration_notes") or ""),
        )
