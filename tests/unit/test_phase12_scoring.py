"""Phase 12 tests: quantitative scorer, dual-scorer logic, export quality gate."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from jobs.scoring.quantitative_scorer import score as quant_score
from schemas.prediction_outcome import PredictionOutcome
from schemas.shared_enums import (
    FlowDirection,
    FlowMagnitude,
    OutcomeStatus,
    ScoringMethod,
)
from tests.unit.payloads import navigation_signal_payload, route_prediction_payload


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_flow(direction: str, net_flow: float) -> dict:
    return {"direction": direction, "net_flow": net_flow}


def _make_outcome(
    *,
    navigation_signal_id: str = "navsig_01J",
    prediction_accuracy: float = 0.75,
    scoring_method: ScoringMethod = ScoringMethod.BLENDED,
    scorer_agreement: float | None = None,
    heuristic_accuracy: float | None = None,
    quantitative_accuracy: float | None = None,
    map_prediction_correct: bool = True,
) -> PredictionOutcome:
    return PredictionOutcome(
        id="outcome_1",
        navigation_signal_id=navigation_signal_id,
        evaluation_window_hours=24,
        prediction_accuracy=prediction_accuracy,
        realized_direction=FlowDirection.INFLOW,
        realized_magnitude=FlowMagnitude.MODERATE,
        map_prediction_correct=map_prediction_correct,
        notes="test",
        created_by_agent="test",
        created_at=datetime(2026, 6, 9, tzinfo=UTC),
        scoring_method=scoring_method,
        scorer_agreement=scorer_agreement,
        heuristic_accuracy=heuristic_accuracy,
        quantitative_accuracy=quantitative_accuracy,
    )


# ---------------------------------------------------------------------------
# Quantitative scorer tests (MAPS-1201)
# ---------------------------------------------------------------------------

class TestQuantitativeScorer:
    def test_matching_inflow_returns_high_score(self):
        flows = [_make_flow("inflow", 1_000_000)] * 3
        result = quant_score(
            predicted_direction="inflow",
            exchange_flows=flows,
            stablecoin_series=[],
        )
        assert result.realized_score >= 0.7

    def test_contradicting_outflow_returns_low_score(self):
        flows = [_make_flow("outflow", -500_000)] * 3
        result = quant_score(
            predicted_direction="inflow",
            exchange_flows=flows,
            stablecoin_series=[],
        )
        assert result.realized_score < 0.4

    def test_empty_series_returns_neutral(self):
        result = quant_score(
            predicted_direction="inflow",
            exchange_flows=[],
            stablecoin_series=[],
        )
        assert result.realized_score == pytest.approx(0.5)

    def test_neutral_observed_direction_is_ambiguous(self):
        flows = [_make_flow("neutral", 0.0)]
        result = quant_score(
            predicted_direction="inflow",
            exchange_flows=flows,
            stablecoin_series=[],
        )
        assert result.realized_score == pytest.approx(0.5)

    def test_measured_deltas_are_recorded(self):
        flows = [_make_flow("inflow", 500_000)]
        result = quant_score(
            predicted_direction="inflow",
            exchange_flows=flows,
            stablecoin_series=[],
        )
        assert "exchange_flows" in result.measured_deltas
        assert result.measured_deltas["exchange_flows"]["net_flow_sum"] == pytest.approx(500_000)

    def test_result_is_always_clamped_to_unit_interval(self):
        flows = [_make_flow("inflow", 1e9)] * 10
        stables = [_make_flow("inflow", 1e9)] * 10
        result = quant_score(
            predicted_direction="inflow",
            exchange_flows=flows,
            stablecoin_series=stables,
        )
        assert 0.0 <= result.realized_score <= 1.0

    def test_scorer_never_imports_story_schemas(self):
        # Verify the module has no imports of story schema or story API modules.
        import inspect
        import jobs.scoring.quantitative_scorer as mod
        src = inspect.getsource(mod)
        forbidden = ("from schemas.navigation_signal", "from clients.e3d_api_client", "supporting_stories")
        for pattern in forbidden:
            assert pattern not in src, f"quantitative_scorer must not import or reference: {pattern}"

    def test_method_tag_is_quantitative(self):
        result = quant_score(
            predicted_direction="inflow",
            exchange_flows=[],
            stablecoin_series=[],
        )
        assert result.method == "quantitative"


# ---------------------------------------------------------------------------
# Dual-scorer integration tests (MAPS-1202)
# ---------------------------------------------------------------------------

class TestDualScorerIntegration:
    """Test score_prediction populates Phase 12 fields correctly."""

    def _run(self, *, exchange_flows=None, stablecoin_activity=None, stories=None):
        from schemas.navigation_signal import NavigationSignal
        from jobs.score_pending_predictions import score_prediction

        signal = NavigationSignal.model_validate(navigation_signal_payload())
        return score_prediction(
            signal=signal,
            route_predictions=[],
            stories=stories or [],
            exchange_flows=exchange_flows or [],
            stablecoin_activity=stablecoin_activity or [],
        )

    def test_heuristic_and_quantitative_accuracy_are_populated(self):
        decision = self._run()
        assert decision.outcome.heuristic_accuracy is not None
        assert decision.outcome.quantitative_accuracy is not None

    def test_scorer_agreement_is_abs_difference(self):
        decision = self._run()
        expected = abs(
            decision.outcome.heuristic_accuracy - decision.outcome.quantitative_accuracy
        )
        assert decision.outcome.scorer_agreement == pytest.approx(expected, abs=1e-6)

    def test_scoring_method_is_blended(self):
        decision = self._run()
        assert decision.outcome.scoring_method == ScoringMethod.BLENDED

    def test_consumer_exposure_defaults_to_zero(self):
        decision = self._run()
        assert decision.outcome.consumer_exposure == 0

    def test_consumer_exposure_propagated(self):
        from schemas.navigation_signal import NavigationSignal
        from jobs.score_pending_predictions import score_prediction

        signal = NavigationSignal.model_validate(navigation_signal_payload())
        decision = score_prediction(
            signal=signal,
            route_predictions=[],
            stories=[],
            exchange_flows=[],
            stablecoin_activity=[],
            consumer_exposure=7,
        )
        assert decision.outcome.consumer_exposure == 7

    def test_disputed_flag_in_notes_when_scorers_disagree_significantly(self):
        # Force a large disagreement: feed strong story support (high heuristic)
        # but contradicting exchange flows (low quantitative).
        from schemas.navigation_signal import NavigationSignal
        from jobs.score_pending_predictions import score_prediction

        signal = NavigationSignal.model_validate(navigation_signal_payload())
        supporting_story = {
            "id": "story_123",
            "story_type": "capital_migration",
            "origin": "stablecoins",
            "destination": "ETH_DEFI",
            "direction": "inflow",
            "created_at": "2026-06-08T01:00:00Z",
        }
        contradicting_flows = [
            {
                "net_flow": -2_000_000,
                "direction": "outflow",
                "created_at": "2026-06-08T02:00:00Z",
            }
        ] * 5

        decision = score_prediction(
            signal=signal,
            route_predictions=[],
            stories=[supporting_story],
            exchange_flows=contradicting_flows,
            stablecoin_activity=[],
        )
        # Both dual-scorer fields must be present regardless of dispute.
        assert decision.outcome.heuristic_accuracy is not None
        assert decision.outcome.quantitative_accuracy is not None

    def test_status_is_disputed_when_agreement_delta_exceeds_threshold(self):
        from schemas.navigation_signal import NavigationSignal
        from jobs.score_pending_predictions import score_prediction, SCORER_DISPUTE_THRESHOLD
        import unittest.mock as mock

        signal = NavigationSignal.model_validate(navigation_signal_payload())

        # Patch both scorer functions so we can control the delta precisely.
        with (
            mock.patch(
                "jobs.score_pending_predictions._score_accuracy",
                return_value=0.9,
            ),
            mock.patch(
                "jobs.score_pending_predictions.quantitative_score",
                return_value=mock.MagicMock(realized_score=0.1),
            ),
        ):
            decision = score_prediction(
                signal=signal,
                route_predictions=[],
                stories=[],
                exchange_flows=[],
                stablecoin_activity=[],
            )

        assert decision.outcome.scorer_agreement == pytest.approx(0.8, abs=1e-6)
        assert decision.outcome.scorer_agreement > SCORER_DISPUTE_THRESHOLD
        assert decision.status == OutcomeStatus.DISPUTED
        assert not decision.outcome.map_prediction_correct


# ---------------------------------------------------------------------------
# Training export quality gate tests (MAPS-1204)
# ---------------------------------------------------------------------------

class TestExportQualityGate:
    def _make_signal(self, signal_id: str = "navsig_01J"):
        from schemas.navigation_signal import NavigationSignal
        payload = navigation_signal_payload(id=signal_id)
        return NavigationSignal.model_validate(payload)

    def test_disputed_outcome_excluded_by_default(self):
        from jobs.export_training_examples import export_training_examples

        signal = self._make_signal()
        outcome = _make_outcome(
            scoring_method=ScoringMethod.BLENDED,
            scorer_agreement=0.8,  # well above 0.35 threshold → disputed
        )
        examples = export_training_examples(
            navigation_signals=[signal],
            prediction_outcomes=[outcome],
            utility_scores=[],
        )
        assert examples == []

    def test_disputed_outcome_included_when_flag_set(self):
        from jobs.export_training_examples import export_training_examples

        signal = self._make_signal()
        outcome = _make_outcome(
            scoring_method=ScoringMethod.BLENDED,
            scorer_agreement=0.8,
        )
        examples = export_training_examples(
            navigation_signals=[signal],
            prediction_outcomes=[outcome],
            utility_scores=[],
            include_disputed=True,
        )
        assert len(examples) == 1

    def test_non_disputed_outcome_passes_through(self):
        from jobs.export_training_examples import export_training_examples

        signal = self._make_signal()
        outcome = _make_outcome(
            scoring_method=ScoringMethod.BLENDED,
            scorer_agreement=0.1,  # small delta → not disputed
        )
        examples = export_training_examples(
            navigation_signals=[signal],
            prediction_outcomes=[outcome],
            utility_scores=[],
        )
        assert len(examples) == 1

    def test_min_scorer_agreement_filter(self):
        from jobs.export_training_examples import export_training_examples

        signal = self._make_signal()
        outcome = _make_outcome(
            scoring_method=ScoringMethod.BLENDED,
            scorer_agreement=0.25,  # not disputed (< 0.35) but agreement only 0.75
        )
        # Require agreement >= 0.9, meaning max delta 0.1 — this should be filtered.
        examples = export_training_examples(
            navigation_signals=[signal],
            prediction_outcomes=[outcome],
            utility_scores=[],
            min_scorer_agreement=0.9,
        )
        assert examples == []

    def test_legacy_outcome_with_none_scorer_agreement_passes_min_agreement_gate(self):
        """Legacy rows (single scorer, scorer_agreement=None) pass through
        min_scorer_agreement to preserve backward compatibility."""
        from jobs.export_training_examples import export_training_examples

        signal = self._make_signal()
        outcome = _make_outcome(
            scoring_method=ScoringMethod.HEURISTIC,
            scorer_agreement=None,
        )
        examples = export_training_examples(
            navigation_signals=[signal],
            prediction_outcomes=[outcome],
            utility_scores=[],
            min_scorer_agreement=0.9,
        )
        assert len(examples) == 1

    def test_scoring_method_provenance_in_example(self):
        from jobs.export_training_examples import export_training_examples

        signal = self._make_signal()
        outcome = _make_outcome(
            scoring_method=ScoringMethod.BLENDED,
            scorer_agreement=0.05,
        )
        examples = export_training_examples(
            navigation_signals=[signal],
            prediction_outcomes=[outcome],
            utility_scores=[],
        )
        assert examples[0]["scoring_method"] == "blended"


# ---------------------------------------------------------------------------
# Schema tests (MAPS-1202 field validation)
# ---------------------------------------------------------------------------

class TestPredictionOutcomeSchema:
    def test_new_fields_have_correct_defaults(self):
        outcome = PredictionOutcome(
            navigation_signal_id="navsig_01J",
            evaluation_window_hours=24,
            prediction_accuracy=0.7,
            realized_direction=FlowDirection.INFLOW,
            realized_magnitude=FlowMagnitude.MODERATE,
            map_prediction_correct=True,
            notes="",
            created_by_agent="test",
            created_at=datetime(2026, 6, 9, tzinfo=UTC),
        )
        assert outcome.consumer_exposure == 0
        assert outcome.scoring_method == ScoringMethod.HEURISTIC
        assert outcome.heuristic_accuracy is None
        assert outcome.quantitative_accuracy is None
        assert outcome.scorer_agreement is None
        assert outcome.exogenous_accuracy is None
        assert outcome.induced_accuracy is None

    def test_consumer_exposure_cannot_be_negative(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            PredictionOutcome(
                navigation_signal_id="navsig_01J",
                evaluation_window_hours=24,
                prediction_accuracy=0.7,
                realized_direction=FlowDirection.INFLOW,
                realized_magnitude=FlowMagnitude.MODERATE,
                map_prediction_correct=True,
                notes="",
                created_by_agent="test",
                created_at=datetime(2026, 6, 9, tzinfo=UTC),
                consumer_exposure=-1,
            )

    def test_scorer_agreement_must_be_in_unit_interval(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            _make_outcome(scorer_agreement=1.5)

    def test_disputed_is_valid_outcome_status(self):
        assert OutcomeStatus.DISPUTED == "disputed"
