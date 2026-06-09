from __future__ import annotations


def navigation_signal_payload(**overrides):
    payload = {
        "id": "navsig_01J",
        "signal_type": "capital_migration",
        "question": "Where is capital likely moving over the next 24 hours?",
        "answer": "Capital appears to be moving toward ETH DeFi.",
        "origin": "stablecoins",
        "destination": "ETH_DEFI",
        "asset_scope": ["ETH", "AAVE"],
        "chain_scope": ["ethereum"],
        "time_horizon_hours": 24,
        "confidence": 0.78,
        "risk_level": "medium",
        "signal_strength": "strong",
        "market_state": "risk_on",
        "supporting_story_ids": ["story_123"],
        "supporting_thesis_ids": ["thesis_789"],
        "supporting_action_ids": [],
        "supporting_outcome_ids": [],
        "evidence": [
            {"type": "story", "id": "story_123", "summary": "Stablecoin inflows increased."}
        ],
        "recommended_route": {
            "origin": "stablecoins",
            "destination": "ETH_DEFI",
            "route_type": "risk_adjusted_capital_rotation",
        },
        "recommended_action": "monitor_or_increase_eth_defi_exposure",
        "created_by_agent": "capital_migration_agent",
        "model": "qwen",
        "adapter": "base-v0",
        "schema_version": "1.0",
        "outcome_status": "pending",
        "created_at": "2026-06-08T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def route_prediction_payload(**overrides):
    payload = {
        "id": "route_01J",
        "navigation_signal_id": "navsig_01J",
        "route_type": "destination_prediction",
        "origin": "stablecoins",
        "destination": "ETH_DEFI",
        "expected_flow_direction": "inflow",
        "expected_flow_magnitude": "moderate",
        "time_horizon_hours": 24,
        "confidence": 0.65,
        "hazards": [],
        "supporting_story_ids": ["story_123"],
        "created_by_agent": "capital_migration_agent",
        "model": "qwen",
        "adapter": "base-v0",
        "schema_version": "1.0",
        "created_at": "2026-06-08T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def story_type_definition_payload(**overrides):
    payload = {
        "story_type": "capital_migration",
        "display_name": "Capital Migration",
        "category": "traffic",
        "human_meaning": "Capital appears to be moving from one destination to another.",
        "agent_meaning": "Use this as evidence for route and destination changes.",
        "inputs": ["wallet_flows", "exchange_flows"],
        "outputs": ["origin", "destination"],
        "example_questions": ["Where is capital migrating?"],
        "related_navigation_signal_types": ["capital_migration", "destination_prediction"],
        "schema_version": "1.0",
        "created_at": "2026-06-08T00:00:00Z",
        "updated_at": "2026-06-08T12:00:00Z",
    }
    payload.update(overrides)
    return payload
