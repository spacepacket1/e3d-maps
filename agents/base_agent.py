from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from pydantic import ValidationError

from clients.qwen_client import QwenClient
from schemas.navigation_signal import NavigationSignal
from schemas.route_prediction import RoutePrediction


class AgentError(RuntimeError):
    """Raised when an agent cannot produce a valid result."""


class AgentParseError(AgentError):
    """Raised when a model response is not valid JSON."""


class AgentValidationError(AgentError):
    """Raised when parsed model output does not match the schema."""


@dataclass(frozen=True)
class AgentRunResult:
    navigation_signal: NavigationSignal | None
    route_predictions: tuple[RoutePrediction, ...] = ()
    raw_response: str | None = None
    parsed_output: Any = None


class BaseAgent:
    def __init__(
        self,
        *,
        agent_name: str,
        question_template: str,
        system_prompt: str,
        agent_prompt: str,
        qwen_client: QwenClient,
        signal_type: str | None = None,
        allowed_signal_types: set[str] | None = None,
        model_name: str | None = None,
        adapter_name: str = "base-v0",
        adapter_path: str | None = None,
    ) -> None:
        self.agent_name = agent_name
        self.question_template = question_template
        self.system_prompt = system_prompt.strip()
        self.agent_prompt = agent_prompt.strip()
        self.qwen_client = qwen_client
        self.signal_type = signal_type
        self.allowed_signal_types = allowed_signal_types or ({signal_type} if signal_type else set())
        self.model_name = model_name or qwen_client.default_model
        self.adapter_name = adapter_name
        self.adapter_path = adapter_path

    @staticmethod
    def load_prompt(relative_path: str) -> str:
        prompt_path = Path(__file__).resolve().parent.parent / relative_path
        return prompt_path.read_text(encoding="utf-8").strip()

    def build_context(self, context: Mapping[str, Any]) -> dict[str, Any]:
        return dict(context)

    def render_question(self, context: Mapping[str, Any]) -> str:
        explicit_question = context.get("question")
        if isinstance(explicit_question, str) and explicit_question.strip():
            return explicit_question.strip()
        return self.question_template.format(
            **{"time_horizon_hours": context.get("time_horizon_hours", 24)}
        )

    def build_prompt(self, context: Mapping[str, Any]) -> str:
        question = self.render_question(context)
        context_block = json.dumps(self.build_context(context), indent=2, sort_keys=True, default=str)
        return (
            f"{self.agent_prompt}\n\n"
            f"Question:\n{question}\n\n"
            f"Context JSON:\n{context_block}\n"
        )

    def call_qwen(self, prompt: str) -> str:
        return self.qwen_client.generate(
            prompt=prompt,
            system_prompt=self.system_prompt,
            model=self.model_name,
            adapter_name=self.adapter_name,
            adapter_path=self.adapter_path,
        )

    def parse_json(self, raw_response: str) -> Any:
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise AgentParseError(f"{self.agent_name} returned invalid JSON: {exc.msg}") from exc

    def validate_output(self, parsed_output: Any, *, question: str) -> AgentRunResult:
        if parsed_output is None:
            return AgentRunResult(
                navigation_signal=None,
                route_predictions=(),
                parsed_output=parsed_output,
            )

        if not isinstance(parsed_output, Mapping):
            raise AgentValidationError(
                f"{self.agent_name} must return null or a JSON object, got {type(parsed_output).__name__}."
            )

        signal_payload, route_payloads = self._extract_payloads(parsed_output)
        try:
            signal = NavigationSignal.model_validate(
                self._prepare_signal_payload(signal_payload, question=question)
            )
        except ValidationError as exc:
            raise AgentValidationError(f"{self.agent_name} returned an invalid navigation signal.") from exc
        self._validate_signal_type(signal.signal_type)

        route_predictions: list[RoutePrediction] = []
        for route_payload in route_payloads:
            try:
                route_predictions.append(
                    RoutePrediction.model_validate(
                        self._prepare_route_prediction_payload(route_payload, signal=signal)
                    )
                )
            except ValidationError as exc:
                raise AgentValidationError(
                    f"{self.agent_name} returned an invalid route prediction."
                ) from exc

        return AgentRunResult(
            navigation_signal=signal,
            route_predictions=tuple(route_predictions),
            parsed_output=parsed_output,
        )

    def run(self, context: Mapping[str, Any]) -> AgentRunResult:
        prompt = self.build_prompt(context)
        question = self.render_question(context)
        raw_response = self.call_qwen(prompt)
        parsed_output = self.parse_json(raw_response)
        result = self.validate_output(parsed_output, question=question)
        return AgentRunResult(
            navigation_signal=result.navigation_signal,
            route_predictions=result.route_predictions,
            raw_response=raw_response,
            parsed_output=result.parsed_output,
        )

    def _extract_payloads(self, parsed_output: Mapping[str, Any]) -> tuple[Mapping[str, Any], list[Mapping[str, Any]]]:
        if "navigation_signal" in parsed_output:
            signal_payload = parsed_output["navigation_signal"]
            route_payloads = parsed_output.get("route_predictions", [])
        else:
            signal_payload = parsed_output
            route_payloads = parsed_output.get("route_predictions", [])

        if not isinstance(signal_payload, Mapping):
            raise AgentValidationError(f"{self.agent_name} output is missing a valid navigation signal object.")
        if route_payloads is None:
            route_payloads = []
        if not isinstance(route_payloads, list) or not all(
            isinstance(item, Mapping) for item in route_payloads
        ):
            raise AgentValidationError(f"{self.agent_name} route_predictions must be an array of objects.")

        return signal_payload, list(route_payloads)

    def _prepare_signal_payload(self, payload: Mapping[str, Any], *, question: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        normalized = dict(payload)
        if not normalized.get("id"):
            normalized["id"] = self._build_id("navsig")
        normalized.setdefault("question", question)
        normalized.setdefault("created_by_agent", self.agent_name)
        normalized.setdefault("model", self.model_name)
        normalized.setdefault("adapter", self.adapter_name)
        normalized.setdefault("schema_version", "1.0")
        normalized.setdefault("outcome_status", "pending")
        if not normalized.get("created_at"):
            normalized["created_at"] = now.isoformat()
        return normalized

    def _prepare_route_prediction_payload(
        self,
        payload: Mapping[str, Any],
        *,
        signal: NavigationSignal,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        normalized = dict(payload)
        if not normalized.get("id"):
            normalized["id"] = self._build_id("route")
        if not normalized.get("navigation_signal_id"):
            normalized["navigation_signal_id"] = signal.id
        normalized.setdefault("created_by_agent", self.agent_name)
        normalized.setdefault("model", self.model_name)
        normalized.setdefault("adapter", self.adapter_name)
        normalized.setdefault("schema_version", "1.0")
        if not normalized.get("created_at"):
            normalized["created_at"] = now.isoformat()
        return normalized

    def _validate_signal_type(self, signal_type: str) -> None:
        if self.allowed_signal_types and signal_type not in self.allowed_signal_types:
            allowed = ", ".join(sorted(self.allowed_signal_types))
            raise AgentValidationError(
                f"{self.agent_name} returned unsupported signal_type {signal_type!r}; expected one of: {allowed}."
            )

    @staticmethod
    def _build_id(prefix: str) -> str:
        return f"{prefix}_{uuid4().hex[:12]}"
