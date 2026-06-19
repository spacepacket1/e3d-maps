from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping

from agents.base_agent import AgentError, BaseAgent
from clients.qwen_client import QwenClient, QwenClientError
from clients.watch_feed_client import WatchFeedClient
from schemas.shared_enums import DraftStatus
from schemas.watch_draft import WatchDraft
from schemas.watch_prediction import WatchPrediction

WATCH_DRAFT_SCHEMA_VERSION = "watch_v1"

_X_POST_LIMIT = 280
_X_TAIL = "Every transaction is traffic. maps.e3d.ai #E3D"
_LINKEDIN_MIN_WORDS = 150


@dataclass(frozen=True)
class WatchDraftResult:
    draft: WatchDraft
    raw_response: str | None = None
    parsed_output: Any = None
    used_fallback: bool = False
    fallback_reason: str | None = None


class WatchDraftGenerator(BaseAgent):
    """Builds a human-facing WatchDraft from a WatchPrediction plus a public
    track-record snapshot.

    The track record is fetched through the public contract
    (``WatchFeedClient.get_calibration``). The X post is always assembled
    deterministically so it leads with the record and stays within the 280-char
    limit; the model supplies the longer-form copy, with a deterministic
    fallback when its output is invalid. v1 drafts are never auto-published.
    """

    def __init__(
        self,
        *,
        qwen_client: QwenClient,
        feed_client: WatchFeedClient | None = None,
        model_name: str | None = None,
        adapter_name: str = "base-v0",
        adapter_path: str | None = None,
    ) -> None:
        super().__init__(
            agent_name="watch_draft_generator",
            question_template="Draft the public copy for this watch prediction.",
            system_prompt=self.load_prompt("prompts/maps_system_prompt.md"),
            agent_prompt=self.load_prompt("prompts/watch_draft_generator.md"),
            qwen_client=qwen_client,
            model_name=model_name,
            adapter_name=adapter_name,
            adapter_path=adapter_path,
        )
        self.feed_client = feed_client

    def generate(
        self,
        prediction: WatchPrediction,
        *,
        track_record: Mapping[str, Any] | None = None,
        now: datetime | None = None,
    ) -> WatchDraftResult:
        created_at = now or datetime.now(UTC)
        snapshot = dict(track_record) if track_record is not None else self._fetch_track_record()
        routing = _build_routing(prediction)
        x_post = _build_x_post(prediction, snapshot)

        prompt = self.build_prompt(self._build_prompt_context(prediction, snapshot))

        raw_response: str | None = None
        parsed_output: Any = None
        try:
            raw_response = self.call_qwen(prompt)
            if not raw_response or not raw_response.strip():
                raise AgentError("empty model output")
            parsed_output = self.parse_json(raw_response)
            headline, analysis, significance, linkedin = self._validate_model_output(parsed_output)
            draft = self._build_draft(
                prediction=prediction,
                headline=headline,
                analysis=analysis,
                significance=significance,
                x_post=x_post,
                linkedin=linkedin,
                snapshot=snapshot,
                routing=routing,
                created_at=created_at,
            )
            return WatchDraftResult(
                draft=draft,
                raw_response=raw_response,
                parsed_output=parsed_output,
                used_fallback=False,
            )
        except (AgentError, QwenClientError, ValueError) as exc:
            fallback = self._build_fallback_draft(
                prediction=prediction,
                x_post=x_post,
                snapshot=snapshot,
                routing=routing,
                created_at=created_at,
            )
            return WatchDraftResult(
                draft=fallback,
                raw_response=raw_response,
                parsed_output=parsed_output,
                used_fallback=True,
                fallback_reason=str(exc),
            )

    # ── track record over the public contract ──────────────────────────────────

    def _fetch_track_record(self) -> dict[str, Any]:
        if self.feed_client is None:
            return {}
        try:
            return dict(self.feed_client.get_calibration(source="watch_agent") or {})
        except Exception:  # noqa: BLE001 - track record is best-effort; never block a draft
            return {}

    # ── prompt context + validation ────────────────────────────────────────────

    def _build_prompt_context(
        self,
        prediction: WatchPrediction,
        snapshot: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "question": self.question_template,
            "prediction": {
                "claim": prediction.claim,
                "signal_type": prediction.signal_type.value,
                "asset_scope": prediction.asset_scope,
                "chain_scope": prediction.chain_scope,
                "realized_direction_expected": prediction.realized_direction_expected.value,
                "magnitude_expected": prediction.magnitude_expected.value,
                "evaluation_window_hours": prediction.evaluation_window_hours,
                "probability": prediction.probability,
            },
            "track_record": dict(snapshot),
        }

    @staticmethod
    def _validate_model_output(parsed_output: Any) -> tuple[str, str, str, str]:
        if not isinstance(parsed_output, Mapping):
            raise ValueError("watch draft output must be a JSON object")

        headline = parsed_output.get("headline")
        if not isinstance(headline, str) or not headline.strip():
            raise ValueError("headline must be a non-empty string")

        analysis = parsed_output.get("analysis")
        significance = parsed_output.get("significance")
        linkedin = parsed_output.get("linkedin_draft")
        for name, value in (("analysis", analysis), ("significance", significance), ("linkedin_draft", linkedin)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")

        if len(linkedin.split()) < _LINKEDIN_MIN_WORDS:
            raise ValueError("linkedin_draft is below the minimum word count")

        return headline.strip(), analysis.strip(), significance.strip(), linkedin.strip()

    # ── draft assembly ──────────────────────────────────────────────────────────

    def _build_draft(
        self,
        *,
        prediction: WatchPrediction,
        headline: str,
        analysis: str,
        significance: str,
        x_post: str,
        linkedin: str,
        snapshot: Mapping[str, Any],
        routing: Mapping[str, Any],
        created_at: datetime,
    ) -> WatchDraft:
        return WatchDraft(
            id=f"watchdraft_{(prediction.id or prediction.idempotency_key)[:18]}",
            watch_prediction_id=prediction.id or prediction.idempotency_key,
            headline=headline,
            analysis=analysis,
            significance=significance,
            x_post=x_post,
            linkedin_draft=linkedin,
            track_record_snapshot=dict(snapshot),
            routing=dict(routing),
            status=DraftStatus.DRAFT,
            created_by_agent=self.agent_name,
            model=self.model_name,
            adapter=self.adapter_name,
            schema_version=WATCH_DRAFT_SCHEMA_VERSION,
            created_at=created_at,
        )

    def _build_fallback_draft(
        self,
        *,
        prediction: WatchPrediction,
        x_post: str,
        snapshot: Mapping[str, Any],
        routing: Mapping[str, Any],
        created_at: datetime,
    ) -> WatchDraft:
        headline = _fallback_headline(prediction)
        analysis = _fallback_analysis(prediction, snapshot)
        significance = _fallback_significance(prediction)
        linkedin = _fallback_linkedin(prediction, snapshot)
        return self._build_draft(
            prediction=prediction,
            headline=headline,
            analysis=analysis,
            significance=significance,
            x_post=x_post,
            linkedin=linkedin,
            snapshot=snapshot,
            routing=routing,
            created_at=created_at,
        )


# ── deterministic builders ──────────────────────────────────────────────────────


def _build_routing(prediction: WatchPrediction) -> dict[str, Any]:
    origin = (
        prediction.chain_scope[0]
        if prediction.chain_scope
        else (prediction.asset_scope[0] if prediction.asset_scope else "unknown")
    )
    destination = prediction.asset_scope[0] if prediction.asset_scope else origin
    return {
        "origin": origin,
        "destination": destination,
        "route_type": prediction.signal_type.value,
        "expected_direction": prediction.realized_direction_expected.value,
        "expected_magnitude": prediction.magnitude_expected.value,
        "window_hours": prediction.evaluation_window_hours,
        "probability": prediction.probability,
        "asset_scope": list(prediction.asset_scope),
        "chain_scope": list(prediction.chain_scope),
        "watch_prediction_id": prediction.id or prediction.idempotency_key,
    }


def _record_lead(snapshot: Mapping[str, Any]) -> str:
    overall = snapshot.get("overall") if isinstance(snapshot, Mapping) else None
    if isinstance(overall, Mapping):
        hit_rate = overall.get("hit_rate")
        total = overall.get("total_scored") or 0
        if hit_rate is not None and total:
            return f"E3D Maps: {round(float(hit_rate) * 100)}% hit rate (n={int(total)})."
    return "E3D Maps navigation intelligence."


def _build_x_post(prediction: WatchPrediction, snapshot: Mapping[str, Any]) -> str:
    lead = _record_lead(snapshot)
    claim = prediction.claim.strip()
    budget = _X_POST_LIMIT - len(lead) - len(_X_TAIL) - 2  # two joining spaces
    if budget < 0:
        budget = 0
    if len(claim) > budget:
        claim = claim[: max(0, budget - 1)].rstrip() + "…"
    post = " ".join(part for part in (lead, claim, _X_TAIL) if part).strip()
    if len(post) > _X_POST_LIMIT:
        post = post[: _X_POST_LIMIT - 1].rstrip() + "…"
    return post


def _fallback_headline(prediction: WatchPrediction) -> str:
    direction = prediction.realized_direction_expected.value
    readable_type = prediction.signal_type.value.replace("_", " ")
    asset = prediction.asset_scope[0] if prediction.asset_scope else "the market"
    return f"E3D Maps reads {direction} flow on {asset} from a {readable_type} signal"


def _fallback_analysis(prediction: WatchPrediction, snapshot: Mapping[str, Any]) -> str:
    return (
        f"{prediction.claim} Maps derives this from a {prediction.signal_type.value.replace('_', ' ')} "
        f"signal with a derived probability of {round(prediction.probability * 100)}% over a "
        f"{prediction.evaluation_window_hours}-hour window. {_record_lead(snapshot)}"
    )


def _fallback_significance(prediction: WatchPrediction) -> str:
    return (
        "Downstream trading and treasury agents routing capital along this corridor should weight the "
        f"expected {prediction.realized_direction_expected.value} flow of "
        f"{prediction.magnitude_expected.value} magnitude when planning execution."
    )


def _fallback_linkedin(prediction: WatchPrediction, snapshot: Mapping[str, Any]) -> str:
    direction = prediction.realized_direction_expected.value
    magnitude = prediction.magnitude_expected.value
    window = prediction.evaluation_window_hours
    readable_type = prediction.signal_type.value.replace("_", " ")
    assets = ", ".join(prediction.asset_scope) or "the broader market"
    chains = ", ".join(prediction.chain_scope) or "Ethereum and connected chains"
    lead = _record_lead(snapshot)
    paragraphs = [
        "Every transaction is traffic, and the road is talking.",
        (
            f"E3D Maps just flagged a {readable_type} signal across {assets} on {chains}. "
            f"{prediction.claim}"
        ),
        (
            f"Reading the road this way, we expect {direction} flow of {magnitude} magnitude over the "
            f"next {window} hours. Maps does not tell you whether to drive — it describes the route, "
            "the traffic, and the hazards, and leaves the decision to the driver. The derived "
            f"probability on this call is {round(prediction.probability * 100)}%, computed from the "
            "source signal's calibrated confidence rather than asserted after the fact."
        ),
        (
            f"{lead} We publish these calls before the outcome is known and settle every one against "
            "on-chain ground truth, so the track record is earned, not claimed. That discipline is what "
            "separates navigation intelligence from narrative."
        ),
        (
            "If you are building autonomous trading, treasury, or research agents, this is the kind of "
            "machine-readable, falsifiable signal you can route on. Watch the flows. Mind the hazards. "
            "Every transaction is traffic."
        ),
    ]
    return "\n\n".join(paragraphs)
