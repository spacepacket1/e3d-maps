from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from pydantic import ValidationError

from agents.base_agent import AgentError, BaseAgent
from clients.qwen_client import QwenClient, QwenClientError
from schemas.story_hypothesis import HypothesisEvidence, StoryHypothesis
from schemas.shared_enums import HypothesisStatus


@dataclass(frozen=True)
class StoryHypothesisAgentResult:
    hypothesis: StoryHypothesis | None
    raw_response: str | None = None
    used_fallback: bool = False
    fallback_reason: str | None = None


class StoryHypothesisAgent(BaseAgent):
    """Proposes a new candidate story type from weak-signal or anomalous patterns.

    Outputs a StoryHypothesis with status="proposed".  A human must advance it
    to "validated" before anything in the story pipeline is changed.
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
            agent_name="story_hypothesis_agent",
            question_template=(
                "Do the provided low-confidence signals point to a recurring "
                "on-chain pattern not yet covered by existing story types?"
            ),
            system_prompt=self.load_prompt("prompts/maps_system_prompt.md"),
            agent_prompt=self.load_prompt("prompts/story_hypothesis_agent.md"),
            qwen_client=qwen_client,
            model_name=model_name,
            adapter_name=adapter_name,
            adapter_path=adapter_path,
        )

    def build_context(self, context: Mapping[str, Any]) -> dict[str, Any]:
        keys = (
            "weak_signals",
            "existing_story_types",
            "signal_count",
            "lookback_days",
        )
        return {key: context[key] for key in keys if key in context}

    def propose(self, context: Mapping[str, Any]) -> StoryHypothesisAgentResult:
        """Run the agent and return a StoryHypothesis."""
        signal_ids = [
            str(s.get("id", "")) for s in context.get("weak_signals", []) if s.get("id")
        ]

        built_context = self.build_context(context)
        prompt = self.build_prompt(built_context)

        raw: str | None = None
        used_fallback = False
        fallback_reason: str | None = None

        try:
            raw = self.qwen_client.generate(
                prompt=prompt,
                model=self.model_name,
                adapter_name=self.adapter_name,
                adapter_path=self.adapter_path,
            )
            parsed = json.loads(raw) or {}
        except QwenClientError as exc:
            used_fallback = True
            fallback_reason = str(exc)
            parsed = {}
        except (ValueError, KeyError):
            used_fallback = True
            fallback_reason = "response was not valid JSON"
            parsed = {}

        # If the model (or fallback) returns no hypothesis, treat it as "no
        # pattern found" — this is valid and expected most cycles.
        proposed_type = str(parsed.get("proposed_story_type", "")).strip()
        if not proposed_type:
            return StoryHypothesisAgentResult(
                hypothesis=None,
                raw_response=raw,
                used_fallback=used_fallback,
                fallback_reason=fallback_reason or "no pattern identified",
            )

        raw_evidence = parsed.get("example_evidence") or []
        evidence = [
            HypothesisEvidence(
                type=str(e.get("type", "signal")),
                id=str(e.get("id", "")),
                summary=str(e.get("summary", "")),
            )
            for e in raw_evidence
            if isinstance(e, dict)
        ]

        try:
            hypothesis = StoryHypothesis(
                proposed_story_type=proposed_type,
                description=str(parsed.get("description", "")),
                detection_rationale=str(parsed.get("detection_rationale", "")),
                supporting_on_chain_patterns=list(
                    parsed.get("supporting_on_chain_patterns") or []
                ),
                related_existing_story_types=list(
                    parsed.get("related_existing_story_types") or []
                ),
                example_evidence=evidence,
                supporting_signal_ids=signal_ids,
                confidence=float(parsed.get("confidence", 0.4)),
                status=HypothesisStatus.PROPOSED,
                created_by_agent=self.agent_name,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        except ValidationError as exc:
            raise AgentError(
                f"StoryHypothesisAgent produced an invalid hypothesis: {exc}"
            ) from exc

        return StoryHypothesisAgentResult(
            hypothesis=hypothesis,
            raw_response=raw,
            used_fallback=used_fallback,
            fallback_reason=fallback_reason,
        )
