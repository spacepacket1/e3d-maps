from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from pydantic import ValidationError

from agents.base_agent import AgentError, BaseAgent
from clients.qwen_client import QwenClient, QwenClientError
from schemas.route_health_report import RouteHealthReport
from schemas.shared_enums import RiskLevel


@dataclass(frozen=True)
class RouteHealthAgentResult:
    report: RouteHealthReport | None
    raw_response: str | None = None
    used_fallback: bool = False
    fallback_reason: str | None = None


class RouteHealthAgent(BaseAgent):
    """Generates a RouteHealthReport for one protocol or chain.

    The summary and traffic_trend are LLM-generated.
    health_score is computed deterministically by the caller from signal ratios
    before this agent is invoked — it is passed in via context and emitted
    verbatim into the report.
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
            agent_name="route_health_agent",
            question_template=(
                "What is the current route health status for {protocol_or_chain}?"
            ),
            system_prompt=self.load_prompt("prompts/maps_system_prompt.md"),
            agent_prompt=self.load_prompt("prompts/route_health_agent.md"),
            qwen_client=qwen_client,
            model_name=model_name,
            adapter_name=adapter_name,
            adapter_path=adapter_path,
        )

    def build_context(self, context: Mapping[str, Any]) -> dict[str, Any]:
        keys = (
            "protocol_or_chain",
            "report_scope",
            "health_score",
            "recent_signals",
            "route_emergence_count",
            "route_closure_count",
            "hazard_signal_count",
            "total_signal_count",
            "time_horizon_hours",
        )
        return {key: context[key] for key in keys if key in context}

    def generate_report(self, context: Mapping[str, Any]) -> RouteHealthAgentResult:
        """Run the agent and return a RouteHealthReport (not a NavigationSignal)."""
        protocol = str(context.get("protocol_or_chain", "unknown"))
        scope = str(context.get("report_scope", "protocol"))
        health_score = float(context.get("health_score", 0.5))
        emergence_count = int(context.get("route_emergence_count", 0))
        closure_count = int(context.get("route_closure_count", 0))
        signal_ids = [
            str(s.get("id", "")) for s in context.get("recent_signals", []) if s.get("id")
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
            parsed = json.loads(raw)
        except QwenClientError as exc:
            used_fallback = True
            fallback_reason = str(exc)
            parsed = self._fallback_output(protocol, health_score)
        except (ValueError, KeyError):
            used_fallback = True
            fallback_reason = "response was not valid JSON"
            parsed = self._fallback_output(protocol, health_score)

        try:
            report = RouteHealthReport(
                protocol_or_chain=protocol,
                report_scope=scope,
                health_score=health_score,
                traffic_trend=str(parsed.get("traffic_trend", "stable")),
                congestion_level=str(parsed.get("congestion_level", RiskLevel.LOW.value)),
                hazard_level=str(parsed.get("hazard_level", RiskLevel.LOW.value)),
                route_emergence_count=emergence_count,
                route_closure_count=closure_count,
                dominant_inflow_source=parsed.get("dominant_inflow_source"),
                dominant_outflow_destination=parsed.get("dominant_outflow_destination"),
                supporting_signal_ids=signal_ids,
                summary=str(parsed.get("summary", f"Route health report for {protocol}.")),
                created_by_agent=self.agent_name,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        except ValidationError as exc:
            raise AgentError(f"RouteHealthAgent produced an invalid report: {exc}") from exc

        return RouteHealthAgentResult(
            report=report,
            raw_response=raw,
            used_fallback=used_fallback,
            fallback_reason=fallback_reason,
        )

    @staticmethod
    def _fallback_output(protocol: str, health_score: float) -> dict[str, Any]:
        trend = "stable" if health_score >= 0.5 else "declining"
        risk = RiskLevel.LOW.value if health_score >= 0.7 else RiskLevel.MEDIUM.value
        return {
            "traffic_trend": trend,
            "congestion_level": risk,
            "hazard_level": risk,
            "summary": (
                f"Route health data for {protocol} compiled from NavigationSignal history. "
                f"Health score: {health_score:.2f}."
            ),
        }
