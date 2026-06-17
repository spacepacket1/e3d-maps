from __future__ import annotations

import pytest

from jobs.score_pending_predictions import (
    _score_congestion_family,
    _score_hazard_family,
    score_prediction,
)
from jobs.scoring.families import (
    SUPPORTED_SIGNAL_TYPES,
    SignalFamily,
    family_for,
)
from schemas.navigation_signal import NavigationSignal
from schemas.shared_enums import FlowDirection, OutcomeStatus
from tests.unit.payloads import navigation_signal_payload


# ---------------------------------------------------------------------------
# Family classifier
# ---------------------------------------------------------------------------

class TestFamilyClassifier:
    def test_flow_types_map_to_flow_family(self):
        for signal_type in ("capital_migration", "destination_prediction", "liquidity_forecast",
                            "route_emergence", "capital_conviction"):
            assert family_for(signal_type) is SignalFamily.FLOW

    def test_hazard_and_congestion_families(self):
        assert family_for("route_hazard") is SignalFamily.HAZARD
        assert family_for("route_closure") is SignalFamily.HAZARD
        assert family_for("congestion_formation") is SignalFamily.CONGESTION

    def test_deferred_types_are_unscorable(self):
        assert family_for("narrative_acceleration") is SignalFamily.UNSCORABLE
        assert family_for("agent_swarm_formation") is SignalFamily.UNSCORABLE

    def test_unknown_type_defaults_to_unscorable(self):
        assert family_for("totally_new_type") is SignalFamily.UNSCORABLE
        assert family_for(None) is SignalFamily.UNSCORABLE

    def test_supported_set_broadened_but_excludes_deferred(self):
        # Coverage jumped from 2 types to the 8 honestly-scorable types.
        assert len(SUPPORTED_SIGNAL_TYPES) == 8
        assert "liquidity_forecast" in SUPPORTED_SIGNAL_TYPES
        assert "route_hazard" in SUPPORTED_SIGNAL_TYPES
        assert "congestion_formation" in SUPPORTED_SIGNAL_TYPES
        assert "narrative_acceleration" not in SUPPORTED_SIGNAL_TYPES
        assert "agent_swarm_formation" not in SUPPORTED_SIGNAL_TYPES


def _hazard_signal(**overrides):
    payload = navigation_signal_payload(
        signal_type=overrides.pop("signal_type", "route_closure"),
        id="navsig_hazard_1",
        origin="ETH",
        destination="ERC20",
        asset_scope=["BiPS"],
        created_at="2026-06-08T00:00:00Z",
        time_horizon_hours=24,
        **overrides,
    )
    return NavigationSignal.model_validate(payload)


def _congestion_signal(**overrides):
    payload = navigation_signal_payload(
        signal_type="congestion_formation",
        id="navsig_congestion_1",
        origin="ETH",
        destination="UNISWAP",
        asset_scope=["UNI"],
        created_at="2026-06-08T00:00:00Z",
        time_horizon_hours=24,
        **overrides,
    )
    return NavigationSignal.model_validate(payload)


# ---------------------------------------------------------------------------
# Hazard family
# ---------------------------------------------------------------------------

class TestHazardFamily:
    def test_danger_evidence_scores_the_hazard_correct(self):
        result = _score_hazard_family(
            signal=_hazard_signal(),
            stories=[
                {
                    "id": "story_danger",
                    "destination": "ERC20",
                    "summary": "BiPS blacklist function and coordinated wallet exit; credible security risk.",
                    "timestamp": "2026-06-08T06:00:00Z",
                }
            ],
            exchange_flows=[
                {"net_flow": -2_000_000, "direction": "outflow", "timestamp": "2026-06-08T05:00:00Z"}
            ] * 3,
            stablecoin_activity=[],
        )
        # Danger story (+0.7) and no recovery (+0.1) => 0.8 heuristic.
        assert result.heuristic_accuracy == pytest.approx(0.8)
        # Quantitative witness saw the predicted outflow.
        assert result.quantitative_accuracy > 0.6
        assert result.realized_direction is FlowDirection.OUTFLOW
        assert result.support_count == 1
        assert result.contradiction_count == 0
        assert "Danger stories" in result.notes_body

    def test_recovery_evidence_penalizes_the_hazard(self):
        result = _score_hazard_family(
            signal=_hazard_signal(),
            stories=[
                {
                    "id": "story_recovery",
                    "destination": "ERC20",
                    "summary": "Liquidity recovered and inflows resumed; the route looks safe again.",
                    "timestamp": "2026-06-08T06:00:00Z",
                }
            ],
            exchange_flows=[],
            stablecoin_activity=[],
        )
        # Recovery contradiction (-0.3), no danger => clamped to 0.0 heuristic.
        assert result.heuristic_accuracy == pytest.approx(0.0)
        assert result.contradiction_count == 1

    def test_out_of_window_story_is_ignored(self):
        result = _score_hazard_family(
            signal=_hazard_signal(),
            stories=[
                {
                    "id": "story_late",
                    "destination": "ERC20",
                    "summary": "BiPS exploit and drain.",
                    "timestamp": "2026-06-09T06:00:00Z",  # after the 24h window
                }
            ],
            exchange_flows=[],
            stablecoin_activity=[],
        )
        assert result.support_count == 0
        assert "story_late" not in result.notes_body

    def test_end_to_end_dispatch_marks_hazard_correct(self):
        decision = score_prediction(
            signal=_hazard_signal(signal_type="route_hazard"),
            route_predictions=[],
            stories=[
                {
                    "id": "story_danger",
                    "destination": "ERC20",
                    "summary": "BiPS blacklist and coordinated exit; security risk flagged.",
                    "timestamp": "2026-06-08T06:00:00Z",
                }
            ],
            exchange_flows=[
                {"net_flow": -1_500_000, "direction": "outflow", "timestamp": "2026-06-08T05:00:00Z"}
            ] * 3,
            stablecoin_activity=[],
        )
        assert decision.status is OutcomeStatus.CORRECT
        assert decision.outcome.map_prediction_correct is True
        assert decision.outcome.created_by_agent == "score_pending_predictions"
        assert "Dual-scorer" in decision.outcome.notes


# ---------------------------------------------------------------------------
# Congestion family
# ---------------------------------------------------------------------------

class TestCongestionFamily:
    def test_persistent_crowding_scores_high(self):
        result = _score_congestion_family(
            signal=_congestion_signal(),
            stories=[
                {
                    "id": "story_crowd",
                    "destination": "UNISWAP",
                    "summary": "Activity surge and volume spike; airdrop drew many holders.",
                    "timestamp": "2026-06-08T03:00:00Z",
                }
            ],
            exchange_flows=[
                {"destination": "UNISWAP", "magnitude": "high", "timestamp": "2026-06-08T04:00:00Z"}
            ] * 3,
            stablecoin_activity=[],
        )
        assert result.heuristic_accuracy == pytest.approx(0.8)
        assert result.quantitative_accuracy == pytest.approx(0.85)
        assert result.support_count == 1
        assert "Active records referencing zone: 3" in result.notes_body

    def test_dissipation_penalizes_and_quiet_window_scores_low(self):
        result = _score_congestion_family(
            signal=_congestion_signal(),
            stories=[
                {
                    "id": "story_quiet",
                    "destination": "UNISWAP",
                    "summary": "The zone went quiet as positions unwound and participants dispersed into a clear slowdown.",
                    "timestamp": "2026-06-08T03:00:00Z",
                }
            ],
            exchange_flows=[],
            stablecoin_activity=[],
        )
        # Dissipation contradiction (-0.3) with no crowding => 0.0 heuristic.
        assert result.heuristic_accuracy == pytest.approx(0.0)
        assert result.contradiction_count == 1
        # No active records => low quantitative witness.
        assert result.quantitative_accuracy == pytest.approx(0.25)
        assert result.realized_direction is FlowDirection.NEUTRAL
