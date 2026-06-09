from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from schemas.navigation_signal import NavigationSignal
from schemas.prediction_outcome import PredictionOutcome
from schemas.route_prediction import RoutePrediction
from schemas.signal_utility_score import SignalUtilityScore
from schemas.story_type_definition import StoryTypeDefinition
from schemas.traffic_state import TrafficState


def normalize_navigation_signal_row(row: dict[str, Any]) -> NavigationSignal:
    payload = {
        "id": row.get("id") or None,
        "signal_type": row["signal_type"],
        "question": row["question"],
        "answer": row["answer"],
        "origin": _optional_string(row.get("origin")),
        "destination": _optional_string(row.get("destination")),
        "asset_scope": _string_list(row.get("asset_scope")),
        "chain_scope": _string_list(row.get("chain_scope")),
        "time_horizon_hours": row["time_horizon_hours"],
        "confidence": row["confidence"],
        "risk_level": row["risk_level"],
        "signal_strength": _optional_string(row.get("signal_strength")),
        "market_state": _optional_string(row.get("market_state")),
        "supporting_story_ids": _string_list(row.get("supporting_story_ids")),
        "supporting_thesis_ids": _string_list(row.get("supporting_thesis_ids")),
        "supporting_action_ids": _string_list(row.get("supporting_action_ids")),
        "supporting_outcome_ids": _string_list(row.get("supporting_outcome_ids")),
        "evidence": _json_array(row.get("evidence_json")),
        "recommended_route": _json_object_or_none(row.get("recommended_route_json")),
        "recommended_action": _optional_string(row.get("recommended_action")),
        "created_by_agent": row["created_by_agent"],
        "model": row.get("model") or "",
        "adapter": row.get("adapter") or "",
        "schema_version": row.get("schema_version") or "",
        "outcome_status": row["outcome_status"],
        "created_at": _parse_datetime(row["created_at"]),
    }
    return NavigationSignal.model_validate(payload, context={"allow_unknown_signal_types": True})


def normalize_route_prediction_row(row: dict[str, Any]) -> RoutePrediction:
    payload = {
        "id": row.get("id") or None,
        "navigation_signal_id": row["navigation_signal_id"],
        "route_type": row["route_type"],
        "origin": row["origin"],
        "destination": row["destination"],
        "expected_flow_direction": row["expected_flow_direction"],
        "expected_flow_magnitude": row["expected_flow_magnitude"],
        "time_horizon_hours": row["time_horizon_hours"],
        "confidence": row["confidence"],
        "hazards": _string_list(row.get("hazards")),
        "supporting_story_ids": _string_list(row.get("supporting_story_ids")),
        "created_by_agent": _optional_string(row.get("created_by_agent")),
        "model": _optional_string(row.get("model")),
        "adapter": _optional_string(row.get("adapter")),
        "schema_version": _optional_string(row.get("schema_version")),
        "created_at": _parse_datetime(row["created_at"]),
    }
    return RoutePrediction.model_validate(payload, context={"allow_unknown_signal_types": True})


def normalize_prediction_outcome_row(row: dict[str, Any]) -> PredictionOutcome:
    payload = {
        "id": row.get("id") or None,
        "navigation_signal_id": row["navigation_signal_id"],
        "route_prediction_id": _optional_string(row.get("route_prediction_id")),
        "evaluation_window_hours": row["evaluation_window_hours"],
        "prediction_accuracy": row["prediction_accuracy"],
        "realized_direction": row["realized_direction"],
        "realized_magnitude": row["realized_magnitude"],
        "map_prediction_correct": bool(row["map_prediction_correct"]),
        "notes": row["notes"],
        "created_by_agent": row["created_by_agent"],
        "created_at": _parse_datetime(row["created_at"]),
    }
    return PredictionOutcome.model_validate(payload)


def normalize_traffic_state_row(row: dict[str, Any]) -> TrafficState:
    payload = {
        "id": row.get("id") or None,
        "scope": row["scope"],
        "market_state": row["market_state"],
        "dominant_flows": _json_array(row.get("dominant_flows_json")),
        "congestion_zones": _string_list(row.get("congestion_zones")),
        "hazards": _string_list(row.get("hazards")),
        "top_destinations": _json_array(row.get("top_destinations_json")),
        "created_by_agent": row["created_by_agent"],
        "created_at": _parse_datetime(row["created_at"]),
    }
    return TrafficState.model_validate(payload)


def normalize_signal_utility_score_row(row: dict[str, Any]) -> SignalUtilityScore:
    payload = {
        "id": row.get("id") or None,
        "navigation_signal_id": row["navigation_signal_id"],
        "sample_size": row["sample_size"],
        "prediction_accuracy": row["prediction_accuracy"],
        "economic_utility": row["economic_utility"],
        "risk_reduction_utility": row["risk_reduction_utility"],
        "confidence_calibration_error": row["confidence_calibration_error"],
        "execution_adjusted_utility": row["execution_adjusted_utility"],
        "final_signal_utility_score": row["final_signal_utility_score"],
        "linked_action_ids": _string_list(row.get("linked_action_ids")),
        "linked_outcome_ids": _string_list(row.get("linked_outcome_ids")),
        "created_at": _parse_datetime(row["created_at"]),
    }
    return SignalUtilityScore.model_validate(payload)


def normalize_story_type_definition_row(row: dict[str, Any]) -> StoryTypeDefinition:
    payload = {
        "story_type": row["story_type"],
        "display_name": row["display_name"],
        "category": row["category"],
        "human_meaning": row["human_meaning"],
        "agent_meaning": row["agent_meaning"],
        "inputs": _string_list(row.get("inputs")),
        "outputs": _string_list(row.get("outputs")),
        "example_questions": _string_list(row.get("example_questions")),
        "related_navigation_signal_types": _string_list(row.get("related_navigation_signal_types")),
        "schema_version": row.get("schema_version") or "",
        "created_at": _parse_datetime(row["created_at"]),
        "updated_at": _parse_datetime(row["updated_at"]),
    }
    return StoryTypeDefinition.model_validate(payload, context={"allow_unknown_signal_types": True})


def _json_array(value: Any) -> list[Any]:
    parsed = _json_value(value)
    if parsed is None:
        return []
    if isinstance(parsed, list):
        return parsed
    raise ValueError("Expected JSON array payload.")


def _json_object_or_none(value: Any) -> dict[str, Any] | None:
    parsed = _json_value(value)
    if parsed is None:
        return None
    if isinstance(parsed, dict):
        return parsed
    raise ValueError("Expected JSON object payload.")


def _json_value(value: Any) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _string_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    raise ValueError("Expected list value.")


def _optional_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        elif "T" in text:
            dt = datetime.fromisoformat(text)
        else:
            dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
