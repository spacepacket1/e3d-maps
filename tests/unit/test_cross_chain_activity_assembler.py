from __future__ import annotations

from datetime import datetime, timedelta

from schemas.navigation_signal import NavigationSignal
from schemas.traffic_state import TrafficState
from services.cross_chain_activity_assembler import assemble_cross_chain_activity_state
from tests.unit.payloads import navigation_signal_payload


BASE_TIME = datetime(2026, 6, 16, 12, 0, 0)


def _make_signal(**overrides) -> NavigationSignal:
    defaults = {
        "id": f"sig_{len(overrides)}",
        "signal_type": "route_emergence",
        "question": "Which routes are gaining traction?",
        "answer": "Ethereum-linked routes are active.",
        "origin": "ETH_DEFI",
        "destination": "BASE",
        "asset_scope": ["ETH"],
        "chain_scope": ["ethereum", "base"],
        "time_horizon_hours": 24,
        "confidence": 0.8,
        "risk_level": "medium",
        "created_at": BASE_TIME,
    }
    defaults.update(overrides)
    return NavigationSignal.model_validate(navigation_signal_payload(**defaults))


def _make_traffic_state(**overrides) -> TrafficState:
    payload = {
        "id": "traffic_01",
        "scope": "global",
        "market_state": "risk_off",
        "dominant_flows": [],
        "congestion_zones": [],
        "hazards": [],
        "top_destinations": [],
        "created_by_agent": "traffic_state_agent",
        "created_at": BASE_TIME,
    }
    payload.update(overrides)
    return TrafficState.model_validate(payload)


def test_binance_labels_normalize_to_binance():
    state = assemble_cross_chain_activity_state(
        [
            _make_signal(
                id="sig_binance",
                signal_type="capital_migration",
                origin="stablecoins",
                destination="BINANCE_EXCHANGE",
                answer="Stablecoins are moving toward Binance.",
            )
        ]
    )

    assert state.top_routes[0].normalized_destination == "binance"
    assert state.top_routes[0].route_class == "cex"


def test_base_arbitrum_and_optimism_group_under_canonical_labels():
    state = assemble_cross_chain_activity_state(
        [
            _make_signal(id="sig_base", destination="BASE_CHAIN", answer="Base flows are active."),
            _make_signal(
                id="sig_arb",
                destination="ARBITRUM_ONE",
                answer="Arbitrum flows are active.",
                created_at=BASE_TIME - timedelta(hours=1),
            ),
            _make_signal(
                id="sig_op",
                destination="OPTIMISM_CHAIN",
                answer="Optimism flows are active.",
                created_at=BASE_TIME - timedelta(hours=2),
            ),
        ]
    )

    normalized = {item.normalized_destination for item in state.top_routes}
    assert {"base", "arbitrum", "optimism"} <= normalized


def test_hazards_outrank_weaker_opportunities_in_hazard_list():
    state = assemble_cross_chain_activity_state(
        [
            _make_signal(
                id="sig_hazard",
                signal_type="route_hazard",
                destination="BINANCE",
                confidence=0.78,
                risk_level="critical",
                answer="Binance-linked route conditions are deteriorating.",
            ),
            _make_signal(
                id="sig_closure",
                signal_type="route_closure",
                destination="SOLANA",
                confidence=0.76,
                risk_level="high",
                created_at=BASE_TIME - timedelta(hours=1),
                answer="One bridge corridor into Solana is closing.",
            ),
            _make_signal(
                id="sig_opportunity",
                signal_type="route_emergence",
                destination="BASE",
                confidence=0.91,
                risk_level="low",
                created_at=BASE_TIME - timedelta(hours=1),
                answer="Base route demand is improving.",
            ),
        ]
    )

    assert [item.destination for item in state.active_hazards] == ["BINANCE", "SOLANA"]
    assert [item.destination for item in state.top_routes] == ["BASE"]


def test_empty_relevant_input_returns_valid_empty_state():
    state = assemble_cross_chain_activity_state(
        [
            _make_signal(
                id="sig_irrelevant",
                signal_type="capital_migration",
                origin="stablecoins",
                destination="ETH_DEFI",
                confidence=0.49,
            )
        ],
        traffic_state=_make_traffic_state(market_state="transitioning"),
    )

    assert state.market_bias == "transitioning"
    assert state.top_routes == []
    assert state.active_hazards == []
    assert state.active_congestion == []
    assert state.top_destinations == []
    assert state.ethereum_outbound_routes == []
    assert state.ethereum_inbound_routes == []
    assert state.supporting_signal_ids == []


def test_ethereum_outbound_and_inbound_routes_are_separated():
    state = assemble_cross_chain_activity_state(
        [
            _make_signal(
                id="sig_outbound",
                origin="ETH_DEFI",
                destination="BASE",
                answer="Capital is leaving Ethereum DeFi for Base.",
            ),
            _make_signal(
                id="sig_inbound",
                origin="BINANCE",
                destination="ETHEREUM",
                answer="Capital is arriving from Binance into Ethereum.",
                created_at=BASE_TIME - timedelta(hours=1),
            ),
            _make_signal(
                id="sig_bridge",
                origin="ETH_DEFI",
                destination="ETH bridge",
                answer="Ethereum capital is exiting through bridge corridors.",
                created_at=BASE_TIME - timedelta(hours=2),
            ),
        ]
    )

    assert [item.destination for item in state.ethereum_outbound_routes] == ["BASE", "ETH bridge"]
    assert [item.origin for item in state.ethereum_inbound_routes] == ["BINANCE"]


def test_bridge_linked_routes_classify_as_bridge():
    state = assemble_cross_chain_activity_state(
        [
            _make_signal(
                id="sig_bridge",
                origin="bridge",
                destination="BASE",
                answer="Bridge-linked Base flows are active.",
            )
        ]
    )

    assert state.top_routes[0].normalized_origin == "cross_chain_bridges"
    assert state.top_routes[0].route_class == "bridge"


def test_top_destinations_only_include_opportunity_routes():
    state = assemble_cross_chain_activity_state(
        [
            _make_signal(
                id="sig_hazard",
                signal_type="route_hazard",
                destination="BINANCE",
                confidence=0.88,
                risk_level="high",
                answer="Binance-linked exits are showing elevated hazard signals.",
            ),
            _make_signal(
                id="sig_congestion",
                signal_type="congestion_formation",
                destination="ARBITRUM",
                confidence=0.77,
                risk_level="medium",
                created_at=BASE_TIME - timedelta(hours=1),
                answer="Arbitrum routes are crowded.",
            ),
            _make_signal(
                id="sig_opportunity",
                signal_type="destination_prediction",
                destination="BASE",
                confidence=0.74,
                risk_level="medium",
                created_at=BASE_TIME - timedelta(hours=2),
                answer="Base remains the most attractive destination.",
            ),
        ]
    )

    assert [item.destination for item in state.top_destinations] == ["BASE"]
