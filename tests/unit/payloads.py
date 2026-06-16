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


def traffic_state_payload(**overrides):
    payload = {
        "id": "traffic_01J",
        "scope": "global",
        "market_state": "transitioning",
        "dominant_flows": [
            {"origin": "stablecoins", "destination": "ETH_DEFI", "strength": "strong"}
        ],
        "congestion_zones": ["CEX"],
        "hazards": ["bridge_risk"],
        "top_destinations": [{"destination": "ETH_DEFI", "confidence": 0.72}],
        "created_by_agent": "maps_runner",
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


def maps_news_brief_payload(**overrides):
    payload = {
        "id": "brief_01J",
        "headline": "Ethereum stays active while bridge conditions start to look crowded",
        "summary": (
            "Flows remain pointed at Ethereum-linked venues and DeFi routes, but fresh signs "
            "of congestion and hazard formation suggest execution quality is weakening across "
            "the busiest corridors."
        ),
        "stance": "crowded",
        "supporting_signal_ids": ["navsig_01J", "navsig_02J"],
        "supporting_story_ids": ["story_123"],
        "supporting_thesis_ids": ["thesis_789"],
        "tags": ["ethereum", "congestion", "hazards_active"],
        "model": "qwen",
        "adapter": "base-v0",
        "schema_version": "1.0",
        "created_at": "2026-06-08T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def cross_chain_activity_state_payload(**overrides):
    route_summary = {
        "origin": "ETH_DEFI",
        "destination": "BASE",
        "normalized_origin": "eth_defi",
        "normalized_destination": "base",
        "signal_type": "route_emergence",
        "confidence": 0.81,
        "risk_level": "medium",
        "signal_strength": 0.81,
        "route_score": 0.92,
        "signal_age_hours": 2.5,
        "route_class": "bridge",
        "summary": "Ethereum-to-Base routes remain active with sustained bridge demand.",
        "time_horizon_hours": 24,
    }
    hazard_summary = {
        "origin": "ETH_DEFI",
        "destination": "BINANCE",
        "normalized_origin": "eth_defi",
        "normalized_destination": "binance",
        "confidence": 0.73,
        "risk_level": "high",
        "signal_age_hours": 1.0,
        "summary": "Binance-linked exits are showing elevated hazard signals.",
    }
    congestion_summary = {
        "origin": "ETH_DEFI",
        "destination": "ARBITRUM",
        "normalized_origin": "eth_defi",
        "normalized_destination": "arbitrum",
        "confidence": 0.69,
        "risk_level": "medium",
        "signal_age_hours": 3.0,
        "summary": "Arbitrum-bound routes are getting more crowded.",
    }
    destination_summary = {
        "destination": "BASE",
        "normalized_destination": "base",
        "confidence": 0.77,
        "supporting_signal_count": 3,
    }
    ethereum_route_summary = {
        "origin": "ETH_DEFI",
        "destination": "BASE",
        "normalized_origin": "eth_defi",
        "normalized_destination": "base",
        "confidence": 0.81,
        "risk_level": "medium",
        "route_class": "bridge",
        "summary": "Base remains the clearest Ethereum outbound route.",
        "signal_age_hours": 2.5,
    }
    payload = {
        "id": "ccas_01J",
        "market_bias": "transitioning",
        "top_routes": [route_summary],
        "active_hazards": [hazard_summary],
        "active_congestion": [congestion_summary],
        "top_destinations": [destination_summary],
        "ethereum_outbound_routes": [ethereum_route_summary],
        "ethereum_inbound_routes": [
            {
                **ethereum_route_summary,
                "origin": "SOLANA",
                "destination": "ETH_DEFI",
                "normalized_origin": "solana",
                "normalized_destination": "eth_defi",
                "summary": "Inbound flows from Solana into Ethereum remain active.",
            }
        ],
        "supporting_signal_ids": ["navsig_01J", "navsig_02J", "navsig_03J"],
        "schema_version": "1.0",
        "created_at": "2026-06-08T01:00:00Z",
    }
    payload.update(overrides)
    return payload
