from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
try:
    from datetime import UTC
except ImportError:  # Python < 3.11
    from datetime import timezone as _tz
    UTC = _tz.utc  # type: ignore[assignment]
from hashlib import sha1
from typing import Any, Mapping, Sequence

from pydantic import ValidationError

from agents.base_agent import AgentError, BaseAgent
from clients.qwen_client import QwenClient, QwenClientError
from schemas.cross_chain_activity_state import CrossChainActivityState
from schemas.maps_news_brief import MapsNewsBrief
from schemas.navigation_signal import NavigationSignal
from schemas.traffic_state import TrafficState

_HAZARD_SIGNAL_TYPES = frozenset({"route_hazard", "route_closure"})
_CONGESTION_SIGNAL_TYPES = frozenset({"congestion_formation"})
_FLOW_SIGNAL_TYPES = frozenset({"capital_migration", "destination_prediction", "route_emergence"})

# Unambiguous chain tokens to guard against in brief text.
# Maps the lowercase word to the set of normalized context labels that permit it.
# Only includes words that are unambiguous in a crypto market context.
_CHAIN_GUARD: dict[str, frozenset[str]] = {
    "solana": frozenset({"solana", "solana_defi", "sol"}),
    "arbitrum": frozenset({"arbitrum", "arbitrum_defi", "arb"}),
    "binance": frozenset({"binance", "bnb", "cex"}),
}


@dataclass(frozen=True)
class MapsNewsAgentResult:
    brief: MapsNewsBrief
    raw_response: str | None = None
    parsed_output: Any = None
    used_fallback: bool = False
    fallback_reason: str | None = None


class MapsNewsAgent(BaseAgent):
    def __init__(
        self,
        *,
        qwen_client: QwenClient,
        model_name: str | None = None,
        adapter_name: str = "base-v0",
        adapter_path: str | None = None,
    ) -> None:
        super().__init__(
            agent_name="maps_news_agent",
            question_template="Write the current Maps News homepage brief.",
            system_prompt=self.load_prompt("prompts/maps_system_prompt.md"),
            agent_prompt=self.load_prompt("prompts/maps_news_agent.md"),
            qwen_client=qwen_client,
            model_name=model_name,
            adapter_name=adapter_name,
            adapter_path=adapter_path,
        )

    def build_context(self, context: Mapping[str, Any]) -> dict[str, Any]:
        traffic_state = _coerce_traffic_state(context.get("traffic_state"))
        cross_chain_state = _coerce_cross_chain_state(context.get("cross_chain_activity_state"))
        previous_brief = _coerce_maps_news_brief(context.get("previous_brief"))
        recent_signals = _coerce_signals(context.get("recent_signals"))

        top_destinations = _compact_top_destinations(
            context.get("top_destinations"),
            cross_chain_state=cross_chain_state,
            traffic_state=traffic_state,
        )
        featured_signals = _select_featured_signals(recent_signals)

        market_state = {
            "traffic_state": traffic_state.market_state.value if traffic_state else None,
            "market_bias": cross_chain_state.market_bias if cross_chain_state else None,
        }
        built: dict[str, Any] = {
            "market_state": market_state,
            "market_bias": market_state["market_bias"] or market_state["traffic_state"] or "neutral",
            "dominant_flows": _compact_dominant_flows(traffic_state),
            "top_destinations": top_destinations,
            "active_hazards": _compact_hazards(cross_chain_state),
            "active_congestion": _compact_congestion(cross_chain_state),
            "top_cross_chain_routes": _compact_top_routes(cross_chain_state),
            "recent_featured_signals": featured_signals,
            "previous_brief": (
                {
                    "headline": previous_brief.headline,
                    "stance": previous_brief.stance,
                    "tags": previous_brief.tags,
                }
                if previous_brief is not None
                else None
            ),
        }
        built["allowed_chains"] = sorted(_extract_allowed_chains(built))
        return built

    def run(self, context: Mapping[str, Any]) -> MapsNewsAgentResult:
        prompt = self.build_prompt(context)
        built_context = self.build_context(context)
        created_at = _derive_created_at(
            traffic_state=_coerce_traffic_state(context.get("traffic_state")),
            cross_chain_state=_coerce_cross_chain_state(context.get("cross_chain_activity_state")),
            previous_brief=_coerce_maps_news_brief(context.get("previous_brief")),
            recent_signals=_coerce_signals(context.get("recent_signals")),
        )

        raw_response: str | None = None
        parsed_output: Any = None
        try:
            raw_response = self.call_qwen(prompt)
            if not raw_response or not raw_response.strip():
                raise ValueError("empty model output")
            parsed_output = self.parse_json(raw_response)
            brief = self._validate_brief_output(parsed_output, built_context=built_context, created_at=created_at)
            return MapsNewsAgentResult(
                brief=brief,
                raw_response=raw_response,
                parsed_output=parsed_output,
                used_fallback=False,
            )
        except (AgentError, QwenClientError, ValueError, ValidationError) as exc:
            fallback = self._build_fallback_brief(context, created_at=created_at)
            return MapsNewsAgentResult(
                brief=fallback,
                raw_response=raw_response,
                parsed_output=parsed_output,
                used_fallback=True,
                fallback_reason=str(exc),
            )

    def _validate_brief_output(
        self,
        parsed_output: Any,
        *,
        built_context: Mapping[str, Any],
        created_at: datetime,
    ) -> MapsNewsBrief:
        if not isinstance(parsed_output, Mapping):
            raise ValueError("Maps News output must be a JSON object")

        payload = dict(parsed_output)
        payload.setdefault("scope", "global")
        payload.setdefault("created_by_agent", self.agent_name)
        payload.setdefault("model", self.model_name)
        payload.setdefault("adapter", self.adapter_name)
        payload.setdefault("schema_version", "1.0")
        payload.setdefault("created_at", created_at.isoformat())
        payload.setdefault("id", _build_brief_id(payload, created_at=created_at))

        brief = MapsNewsBrief.model_validate(payload)
        _validate_model_brief_shape(brief)
        _validate_supporting_references(brief, built_context=built_context)
        _validate_chain_mentions(brief, allowed_chains=frozenset(built_context.get("allowed_chains") or []))
        return brief

    def _build_fallback_brief(
        self,
        context: Mapping[str, Any],
        *,
        created_at: datetime,
    ) -> MapsNewsBrief:
        traffic_state = _coerce_traffic_state(context.get("traffic_state"))
        cross_chain_state = _coerce_cross_chain_state(context.get("cross_chain_activity_state"))
        recent_signals = _coerce_signals(context.get("recent_signals"))
        featured_signals = _select_featured_signals(recent_signals)

        top_signal_ids = [item["id"] for item in featured_signals[:8] if item.get("id")]
        story_ids = _ordered_unique_ids(
            story_id
            for signal in recent_signals
            for story_id in signal.supporting_story_ids
            if signal.id in top_signal_ids
        )
        thesis_ids = _ordered_unique_ids(
            thesis_id
            for signal in recent_signals
            for thesis_id in signal.supporting_thesis_ids
            if signal.id in top_signal_ids
        )

        if cross_chain_state and cross_chain_state.active_hazards:
            top_hazard = cross_chain_state.active_hazards[0]
            market_bias = cross_chain_state.market_bias
            destination = top_hazard.normalized_destination
            headline = f"Routes are active with elevated risk on {destination}"
            summary = (
                f"Maps still reads {market_bias.replace('_', ' ')} conditions overall, but "
                f"{top_hazard.summary.rstrip('.')} is keeping execution risk elevated on the "
                f"busiest route into {destination}."
            )
            stance = "cautious" if market_bias != "risk_off" else "risk_off"
            tags = _fallback_tags(destination, include_hazard=True, include_congestion=False)
        elif cross_chain_state and cross_chain_state.top_routes:
            top_route = cross_chain_state.top_routes[0]
            market_bias = cross_chain_state.market_bias
            destination = top_route.normalized_destination
            headline = f"{destination} leads route activity"
            summary = (
                f"Maps is tracking {market_bias.replace('_', ' ')} conditions, with "
                f"{top_route.summary.rstrip('.')} standing out as the clearest active corridor "
                f"across current cross-chain traffic."
            )
            stance = "neutral" if market_bias == "transitioning" else market_bias
            tags = _fallback_tags(
                destination,
                include_hazard=False,
                include_congestion=bool(cross_chain_state.active_congestion),
            )
        elif traffic_state is not None:
            market_bias = traffic_state.market_state.value
            headline = f"Maps is tracking {market_bias.replace('_', ' ')} conditions"
            flow = traffic_state.dominant_flows[0] if traffic_state.dominant_flows else None
            if flow is None:
                summary = (
                    "The latest traffic snapshot is building, with directional evidence still thin "
                    "enough that route leadership remains provisional."
                )
            else:
                summary = (
                    f"The strongest current flow still runs from {flow.origin} toward "
                    f"{flow.destination}, giving Maps a compact read on where conditions are "
                    f"leaning across active routes."
                )
            stance = market_bias if market_bias != "transitioning" else "neutral"
            tags = _fallback_tags(
                _fallback_destination_from_traffic(traffic_state),
                include_hazard=bool(traffic_state.hazards),
                include_congestion=bool(traffic_state.congestion_zones),
            )
        else:
            headline = "Maps is warming up with early route reads still taking shape"
            summary = "Signal data is accumulating. Check back shortly for a cleaner read on active routes and execution conditions."
            stance = "neutral"
            tags = ["maps"]

        payload = {
            "id": _build_brief_id({"headline": headline, "summary": summary, "stance": stance}, created_at=created_at),
            "scope": "global",
            "headline": headline,
            "summary": summary[:420],
            "stance": stance,
            "supporting_signal_ids": top_signal_ids[:8],
            "supporting_story_ids": story_ids,
            "supporting_thesis_ids": thesis_ids,
            "tags": tags[:6],
            "created_by_agent": self.agent_name,
            "model": self.model_name,
            "adapter": self.adapter_name,
            "schema_version": "1.0",
            "created_at": created_at,
        }
        return MapsNewsBrief.model_validate(payload)


def _coerce_traffic_state(value: Any) -> TrafficState | None:
    if value is None or isinstance(value, TrafficState):
        return value
    if isinstance(value, Mapping):
        return TrafficState.model_validate(value)
    raise TypeError("traffic_state must be a TrafficState, mapping, or None")


def _coerce_cross_chain_state(value: Any) -> CrossChainActivityState | None:
    if value is None or isinstance(value, CrossChainActivityState):
        return value
    if isinstance(value, Mapping):
        return CrossChainActivityState.model_validate(value)
    raise TypeError("cross_chain_activity_state must be a CrossChainActivityState, mapping, or None")


def _coerce_maps_news_brief(value: Any) -> MapsNewsBrief | None:
    if value is None or isinstance(value, MapsNewsBrief):
        return value
    if isinstance(value, Mapping):
        return MapsNewsBrief.model_validate(value)
    raise TypeError("previous_brief must be a MapsNewsBrief, mapping, or None")


def _coerce_signals(value: Any) -> list[NavigationSignal]:
    if value in (None, ()):
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError("recent_signals must be a sequence of NavigationSignal payloads")
    signals: list[NavigationSignal] = []
    for item in value:
        if isinstance(item, NavigationSignal):
            signals.append(item)
        elif isinstance(item, Mapping):
            signals.append(
                NavigationSignal.model_validate(
                    item,
                    context={"allow_unknown_signal_types": True},
                )
            )
        else:
            raise TypeError("recent_signals entries must be NavigationSignal models or mappings")
    return signals


def _compact_dominant_flows(traffic_state: TrafficState | None) -> list[dict[str, str]]:
    if traffic_state is None:
        return []
    return [
        {
            "origin": flow.origin,
            "destination": flow.destination,
            "strength": flow.strength.value,
        }
        for flow in traffic_state.dominant_flows[:3]
    ]


def _compact_top_destinations(
    value: Any,
    *,
    cross_chain_state: CrossChainActivityState | None,
    traffic_state: TrafficState | None,
) -> list[dict[str, Any]]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        result: list[dict[str, Any]] = []
        for item in value[:6]:
            if isinstance(item, Mapping):
                result.append(dict(item))
        if result:
            return result

    if cross_chain_state is not None and cross_chain_state.top_destinations:
        return [
            {
                "destination": item.destination,
                "normalized_destination": item.normalized_destination,
                "confidence": item.confidence,
                "supporting_signal_count": item.supporting_signal_count,
            }
            for item in cross_chain_state.top_destinations[:3]
        ]

    if traffic_state is not None and traffic_state.top_destinations:
        return [
            {
                "destination": item.destination,
                "confidence": item.confidence,
            }
            for item in traffic_state.top_destinations[:3]
        ]
    return []


def _compact_hazards(cross_chain_state: CrossChainActivityState | None) -> list[dict[str, Any]]:
    if cross_chain_state is None:
        return []
    return [
        {
            "origin": item.origin,
            "destination": item.destination,
            "normalized_destination": item.normalized_destination,
            "confidence": item.confidence,
            "risk_level": item.risk_level.value,
            "summary": item.summary,
        }
        for item in cross_chain_state.active_hazards[:3]
    ]


def _compact_congestion(cross_chain_state: CrossChainActivityState | None) -> list[dict[str, Any]]:
    if cross_chain_state is None:
        return []
    return [
        {
            "origin": item.origin,
            "destination": item.destination,
            "normalized_destination": item.normalized_destination,
            "confidence": item.confidence,
            "risk_level": item.risk_level.value,
            "summary": item.summary,
        }
        for item in cross_chain_state.active_congestion[:2]
    ]


def _compact_top_routes(cross_chain_state: CrossChainActivityState | None) -> list[dict[str, Any]]:
    if cross_chain_state is None:
        return []
    return [
        {
            "origin": item.origin,
            "destination": item.destination,
            "normalized_origin": item.normalized_origin,
            "normalized_destination": item.normalized_destination,
            "signal_type": item.signal_type,
            "confidence": item.confidence,
            "risk_level": item.risk_level.value,
            "route_class": item.route_class,
            "summary": item.summary,
        }
        for item in cross_chain_state.top_routes[:3]
    ]


def _select_featured_signals(signals: Sequence[NavigationSignal]) -> list[dict[str, Any]]:
    sorted_signals = sorted(
        signals,
        key=lambda signal: (-signal.confidence, -_timestamp(signal.created_at), signal.id or ""),
    )
    selected: list[NavigationSignal] = []
    hazard_count = 0
    congestion_count = 0
    flow_count = 0
    for signal in sorted_signals:
        if signal.signal_type in _HAZARD_SIGNAL_TYPES:
            if hazard_count >= 3:
                continue
            hazard_count += 1
        elif signal.signal_type in _CONGESTION_SIGNAL_TYPES:
            if congestion_count >= 2:
                continue
            congestion_count += 1
        elif signal.signal_type in _FLOW_SIGNAL_TYPES:
            if flow_count >= 3:
                continue
            flow_count += 1
        else:
            continue

        selected.append(signal)
        if len(selected) >= 8:
            break

    return [
        {
            "id": signal.id,
            "signal_type": signal.signal_type,
            "origin": signal.origin,
            "destination": signal.destination,
            "confidence": signal.confidence,
            "risk_level": signal.risk_level.value,
            "summary": signal.answer,
            "supporting_story_ids": signal.supporting_story_ids,
            "supporting_thesis_ids": signal.supporting_thesis_ids,
        }
        for signal in selected
    ]


def _extract_allowed_chains(built: dict[str, Any]) -> set[str]:
    """Return normalized chain/label names present in structured context fields only.

    Deliberately excludes free-text signal summaries (answer text), which may
    mention chains not reflected in the structured origin/destination data.
    """
    chains: set[str] = set()

    def _add(val: str | None) -> None:
        if val:
            chains.add(val.lower().strip())

    for route in built.get("top_cross_chain_routes") or []:
        for key in ("origin", "destination", "normalized_origin", "normalized_destination"):
            _add(route.get(key))
    for item in built.get("active_hazards") or []:
        for key in ("origin", "destination", "normalized_origin", "normalized_destination"):
            _add(item.get(key))
    for item in built.get("active_congestion") or []:
        for key in ("origin", "destination", "normalized_origin", "normalized_destination"):
            _add(item.get(key))
    for dest in built.get("top_destinations") or []:
        for key in ("destination", "normalized_destination"):
            _add(dest.get(key))
    for flow in built.get("dominant_flows") or []:
        for key in ("origin", "destination"):
            _add(flow.get(key))
    # Use only origin/destination from signals — NOT "summary" (answer text)
    for sig in built.get("recent_featured_signals") or []:
        for key in ("origin", "destination"):
            _add(sig.get(key))

    chains.discard("unknown")
    chains.discard("")
    return chains


def _validate_chain_mentions(brief: "MapsNewsBrief", *, allowed_chains: frozenset[str]) -> None:
    """Raise ValueError if the brief mentions a chain absent from structured context.

    Guards against the model hallucinating chain names it read from signal
    answer text, which are not reflected in the flow graph or cross-chain state.
    """
    text = (brief.headline + " " + brief.summary).lower()
    for chain_word, allowed_aliases in _CHAIN_GUARD.items():
        if re.search(r"\b" + re.escape(chain_word) + r"\b", text):
            if not (allowed_aliases & allowed_chains):
                raise ValueError(
                    f"Brief mentions '{chain_word}' but no {chain_word!r} signals "
                    "are present in the structured context"
                )


def _validate_supporting_references(
    brief: MapsNewsBrief,
    *,
    built_context: Mapping[str, Any],
) -> None:
    featured_signals = built_context.get("recent_featured_signals") or []
    allowed_signal_ids = {str(item["id"]) for item in featured_signals if item.get("id")}
    allowed_story_ids = {
        str(story_id)
        for item in featured_signals
        for story_id in item.get("supporting_story_ids", [])
    }
    allowed_thesis_ids = {
        str(thesis_id)
        for item in featured_signals
        for thesis_id in item.get("supporting_thesis_ids", [])
    }

    if not set(brief.supporting_signal_ids).issubset(allowed_signal_ids):
        raise ValueError("supporting_signal_ids must come from the featured signal context")
    if not set(brief.supporting_story_ids).issubset(allowed_story_ids):
        raise ValueError("supporting_story_ids must come from the featured signal context")
    if not set(brief.supporting_thesis_ids).issubset(allowed_thesis_ids):
        raise ValueError("supporting_thesis_ids must come from the featured signal context")


def _validate_model_brief_shape(brief: MapsNewsBrief) -> None:
    if not 20 <= len(brief.headline) <= 160:
        raise ValueError("headline must be 20-160 characters")
    if not 80 <= len(brief.summary) <= 600:
        raise ValueError("summary must be 80-600 characters")
    if not 1 <= len(brief.tags) <= 6:
        raise ValueError("tags must contain 1 to 6 items")


def _build_brief_id(payload: Mapping[str, Any], *, created_at: datetime) -> str:
    digest = sha1(
        "|".join(
            [
                str(payload.get("headline", "")).strip(),
                str(payload.get("summary", "")).strip(),
                str(payload.get("stance", "")).strip(),
                created_at.isoformat(),
            ]
        ).encode("utf-8")
    ).hexdigest()
    return f"brief_{digest[:12]}"


def _derive_created_at(
    *,
    traffic_state: TrafficState | None,
    cross_chain_state: CrossChainActivityState | None,
    previous_brief: MapsNewsBrief | None,
    recent_signals: Sequence[NavigationSignal],
) -> datetime:
    timestamps: list[datetime] = []
    if traffic_state is not None:
        timestamps.append(traffic_state.created_at)
    if cross_chain_state is not None:
        timestamps.append(cross_chain_state.created_at)
    if previous_brief is not None:
        timestamps.append(previous_brief.created_at)
    timestamps.extend(signal.created_at for signal in recent_signals)
    if not timestamps:
        return datetime.now(UTC)
    return max(_to_utc(timestamp) for timestamp in timestamps)


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _timestamp(value: datetime) -> float:
    return _to_utc(value).timestamp()


def _ordered_unique_ids(values: Sequence[str] | Any) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _fallback_tags(
    destination: str | None,
    *,
    include_hazard: bool,
    include_congestion: bool,
) -> list[str]:
    tags: list[str] = []
    if destination:
        tags.append(destination)
    if include_hazard:
        tags.append("hazards_active")
    if include_congestion:
        tags.append("congestion")
    if not tags:
        tags.append("maps")
    return tags


def _fallback_destination_from_traffic(traffic_state: TrafficState) -> str | None:
    if traffic_state.top_destinations:
        return traffic_state.top_destinations[0].destination.lower()
    if traffic_state.dominant_flows:
        return traffic_state.dominant_flows[0].destination.lower()
    return None
