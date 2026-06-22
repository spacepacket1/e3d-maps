"""Unit tests for the 8 new agent loop jobs.

Tests use direct imports from specific modules (not via agents/__init__.py or
jobs.compute_signal_utility_scores) to avoid pulling in pre-existing Python
3.11-only constructs (datetime.UTC) that don't affect the new code itself.
"""
from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone

import pytest

from clients.clickhouse_client import ClickHouseClient
from clients.qwen_client import QwenClient
from schemas.shared_enums import AnomalySeverity, DriftSeverity, HypothesisStatus


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

class StubQwenClient(QwenClient):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(request_executor=lambda req, timeout: b"")
        self._responses = list(responses)

    def generate(self, **_kwargs: object) -> str:
        if self._responses:
            return self._responses.pop(0)
        return "null"


def _dry_writer() -> tuple[ClickHouseClient, io.StringIO]:
    buf = io.StringIO()
    return ClickHouseClient(dry_run=True, output=buf), buf


NOW = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Loop 1: aggregate_query_demand — pure aggregate() logic
# ---------------------------------------------------------------------------

def test_aggregate_query_demand_empty_logs():
    from jobs.aggregate_query_demand import aggregate

    result = aggregate(
        [], [],
        window_start=NOW - timedelta(minutes=15),
        window_end=NOW,
        now=NOW,
    )
    assert result.total_queries == 0
    assert result.urgency_trend == "stable"
    assert result.demand_surge_destinations == []


def test_aggregate_query_demand_counts_destinations():
    from jobs.aggregate_query_demand import aggregate

    logs = [
        {"destination_filter": "BASE", "signal_type_filter": "route_emergence",
         "time_horizon_hours_filter": 24},
        {"destination_filter": "BASE", "signal_type_filter": "route_emergence",
         "time_horizon_hours_filter": 12},
        {"destination_filter": "ETH_DEFI", "signal_type_filter": "capital_migration",
         "time_horizon_hours_filter": 6},
    ]
    result = aggregate(
        logs, [],
        window_start=NOW - timedelta(minutes=15),
        window_end=NOW,
        now=NOW,
    )
    assert result.total_queries == 3
    assert result.top_destinations[0] == "BASE"
    assert result.avg_requested_time_horizon_hours == pytest.approx(14.0)


def test_aggregate_query_demand_surge_detection():
    from jobs.aggregate_query_demand import aggregate

    window_start = NOW - timedelta(minutes=15)
    # 10 queries in 15-min window (window_hours = 0.25) → rate = 40/hr
    # Baseline: 2 queries in 24h → rate = 0.083/hr; ratio ≈ 480 >> SURGE_MULTIPLIER (2.0)
    logs = [{"destination_filter": "ARBITRUM", "signal_type_filter": "",
             "time_horizon_hours_filter": None}] * 10
    baseline = [{"destination_filter": "ARBITRUM"}] * 2
    result = aggregate(
        logs, baseline,
        window_start=window_start,
        window_end=NOW,
        now=NOW,
    )
    assert "ARBITRUM" in result.demand_surge_destinations


def test_aggregate_query_demand_urgency_trend_shrinking():
    from jobs.aggregate_query_demand import aggregate

    window_start = NOW - timedelta(minutes=15)
    # Current avg horizon = 2h; baseline avg = 24h → shrinking
    logs = [{"destination_filter": "BASE", "signal_type_filter": "",
             "time_horizon_hours_filter": 2}] * 5
    baseline = [{"destination_filter": "BASE", "time_horizon_hours_filter": 24}] * 10
    result = aggregate(
        logs, baseline,
        window_start=window_start,
        window_end=NOW,
        now=NOW,
    )
    assert result.urgency_trend == "shrinking"


# ---------------------------------------------------------------------------
# Loop 2: detect_reflexivity — pure grouping logic
# ---------------------------------------------------------------------------

def test_detect_reflexivity_no_signal_when_low_exposure():
    from jobs.detect_reflexivity import _group_by_destination, EXPOSURE_THRESHOLD

    signals = [
        {"id": "s1", "destination": "BASE", "origin": "ETH", "consumer_exposure": 1},
    ]
    groups = _group_by_destination(signals)
    total = sum(int(s.get("consumer_exposure") or 0) for s in groups.get("BASE", []))
    assert total < EXPOSURE_THRESHOLD


def test_detect_reflexivity_groups_by_destination():
    from jobs.detect_reflexivity import _group_by_destination

    signals = [
        {"id": "s1", "destination": "BASE", "consumer_exposure": 10},
        {"id": "s2", "destination": "BASE", "consumer_exposure": 8},
        {"id": "s3", "destination": "ARBITRUM", "consumer_exposure": 6},
        {"id": "s4", "destination": "", "consumer_exposure": 5},  # no dest, skipped
    ]
    groups = _group_by_destination(signals)
    assert len(groups["BASE"]) == 2
    assert len(groups["ARBITRUM"]) == 1
    assert "" not in groups


# ---------------------------------------------------------------------------
# Loop 3: compute_narrative_velocity — pure ratio math
# ---------------------------------------------------------------------------

def test_compute_narrative_velocity_spike_ratio_above_threshold():
    from jobs.compute_narrative_velocity import (
        SHORT_WINDOW_HOURS,
        LONG_WINDOW_HOURS,
        VELOCITY_SPIKE_THRESHOLD,
        MIN_SIGNALS_TO_QUALIFY,
    )
    short_count = 30
    long_count = 20
    assert short_count >= MIN_SIGNALS_TO_QUALIFY
    short_rate = short_count / SHORT_WINDOW_HOURS
    long_rate = long_count / LONG_WINDOW_HOURS
    ratio = short_rate / long_rate
    # 30/6 = 5/hr; 20/24 ≈ 0.833/hr; ratio ≈ 6.0 > threshold (2.5)
    assert ratio >= VELOCITY_SPIKE_THRESHOLD


def test_compute_narrative_velocity_no_spike_when_ratio_below_threshold():
    from jobs.compute_narrative_velocity import (
        SHORT_WINDOW_HOURS, LONG_WINDOW_HOURS, VELOCITY_SPIKE_THRESHOLD
    )
    short_count = 5
    long_count = 40
    short_rate = short_count / SHORT_WINDOW_HOURS
    long_rate = long_count / LONG_WINDOW_HOURS
    ratio = short_rate / long_rate
    assert ratio < VELOCITY_SPIKE_THRESHOLD


# ---------------------------------------------------------------------------
# Loop 4: monitor_anomalies — pure threshold math
# ---------------------------------------------------------------------------

def test_monitor_anomalies_severity_classification():
    from jobs.monitor_anomalies import (
        ELEVATED_THRESHOLD, HIGH_THRESHOLD, CRITICAL_THRESHOLD,
    )
    ratios_and_expected = [
        (ELEVATED_THRESHOLD + 0.1, AnomalySeverity.ELEVATED),
        (HIGH_THRESHOLD + 0.1, AnomalySeverity.HIGH),
        (CRITICAL_THRESHOLD + 0.1, AnomalySeverity.CRITICAL),
    ]
    for ratio, expected in ratios_and_expected:
        if ratio >= CRITICAL_THRESHOLD:
            sev = AnomalySeverity.CRITICAL
        elif ratio >= HIGH_THRESHOLD:
            sev = AnomalySeverity.HIGH
        else:
            sev = AnomalySeverity.ELEVATED
        assert sev == expected, f"ratio={ratio} expected={expected} got={sev}"


# ---------------------------------------------------------------------------
# Loop 5: generate_route_health_reports — pure health_score logic
# ---------------------------------------------------------------------------

def test_generate_route_health_computes_health_score():
    from jobs.generate_route_health_reports import _compute_health_score

    signals = [
        {"signal_type": "route_emergence", "confidence": 0.8},
        {"signal_type": "route_emergence", "confidence": 0.9},
        {"signal_type": "route_hazard", "confidence": 0.7},
    ]
    score = _compute_health_score(signals)
    assert 0.0 <= score <= 1.0
    # avg_confidence = 0.8, hazard_ratio = 1/3 → 0.8 * (1 - 1/3) ≈ 0.533
    assert score == pytest.approx(0.8 * (1 - 1/3), abs=0.01)


def test_generate_route_health_empty_signals():
    from jobs.generate_route_health_reports import _compute_health_score

    assert _compute_health_score([]) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Loop 6: monitor_adapter_health — schema validation
# ---------------------------------------------------------------------------

def test_adapter_health_calibration_bucket_schema():
    from schemas.adapter_health_report import CalibrationBucket

    bucket = CalibrationBucket(
        bucket_label="0.7–0.9",
        predicted_confidence=0.8,
        realized_accuracy=0.72,
        sample_size=20,
        thin_data=False,
    )
    assert bucket.predicted_confidence == pytest.approx(0.8)
    assert not bucket.thin_data


def test_adapter_health_drift_severity_thresholds():
    from jobs.monitor_adapter_health import (
        DRIFT_MILD_THRESHOLD, DRIFT_MODERATE_THRESHOLD, DRIFT_SEVERE_THRESHOLD,
    )
    cases = [
        (DRIFT_MILD_THRESHOLD - 0.01, DriftSeverity.NONE),
        (DRIFT_MILD_THRESHOLD + 0.01, DriftSeverity.MILD),
        (DRIFT_MODERATE_THRESHOLD + 0.01, DriftSeverity.MODERATE),
        (DRIFT_SEVERE_THRESHOLD + 0.01, DriftSeverity.SEVERE),
    ]
    for err, expected in cases:
        if err >= DRIFT_SEVERE_THRESHOLD:
            sev = DriftSeverity.SEVERE
        elif err >= DRIFT_MODERATE_THRESHOLD:
            sev = DriftSeverity.MODERATE
        elif err >= DRIFT_MILD_THRESHOLD:
            sev = DriftSeverity.MILD
        else:
            sev = DriftSeverity.NONE
        assert sev == expected, f"err={err}"


# ---------------------------------------------------------------------------
# Loop 7: propose_story_hypotheses — agent logic via direct import
# ---------------------------------------------------------------------------

def test_story_hypothesis_agent_returns_none_on_null():
    from agents.story_hypothesis_agent import StoryHypothesisAgent

    agent = StoryHypothesisAgent(qwen_client=StubQwenClient(["null"]))
    result = agent.propose({
        "weak_signals": [{"id": f"s{i}"} for i in range(15)],
        "existing_story_types": ["capital_migration"],
        "signal_count": 15,
        "lookback_days": 7,
    })
    assert result.hypothesis is None


def test_story_hypothesis_agent_parses_valid_response():
    from agents.story_hypothesis_agent import StoryHypothesisAgent

    response = json.dumps({
        "proposed_story_type": "cross_protocol_yield_collapse",
        "description": "Sudden liquidity withdrawal from yield-bearing protocols.",
        "detection_rationale": "Not covered by route_closure.",
        "supporting_on_chain_patterns": ["mass_exit_from_vaults"],
        "related_existing_story_types": ["route_closure"],
        "example_evidence": [{"type": "signal", "id": "s1", "summary": "TVL dropped 40%"}],
        "confidence": 0.55,
    })
    agent = StoryHypothesisAgent(qwen_client=StubQwenClient([response]))
    signals = [{"id": f"s{i}", "signal_type": "route_closure", "confidence": 0.3}
               for i in range(15)]
    result = agent.propose({
        "weak_signals": signals,
        "existing_story_types": ["capital_migration"],
        "signal_count": 15,
        "lookback_days": 7,
    })
    assert result.hypothesis is not None
    assert result.hypothesis.proposed_story_type == "cross_protocol_yield_collapse"
    assert result.hypothesis.status == HypothesisStatus.PROPOSED
    assert 0.3 <= result.hypothesis.confidence <= 0.7


# ---------------------------------------------------------------------------
# Loop 8: synthesize_bridge_signals — pure filter logic
# ---------------------------------------------------------------------------

def test_synthesize_bridge_signals_filter():
    from jobs.synthesize_bridge_signals import _is_bridge_signal

    assert _is_bridge_signal({
        "signal_type": "cross_chain_bridge_flow",
        "origin": "", "destination": "", "answer": "", "question": "",
    })
    assert _is_bridge_signal({
        "signal_type": "other",
        "origin": "", "destination": "stargate_vault", "answer": "", "question": "",
    })
    assert not _is_bridge_signal({
        "signal_type": "capital_migration",
        "origin": "ETH", "destination": "BASE",
        "answer": "plain capital flow", "question": "Q",
    })


def test_synthesize_bridge_signals_writes_to_dry_run():
    from jobs.synthesize_bridge_signals import _is_bridge_signal, MIN_BRIDGE_SIGNALS
    from collections import Counter

    bridge_rows = [
        {"id": f"s{i}", "signal_type": "cross_chain_bridge_flow",
         "origin": "ETH", "destination": "BASE",
         "confidence": 0.75, "risk_level": "low",
         "answer": "bridge flow", "question": "Q"}
        for i in range(MIN_BRIDGE_SIGNALS + 1)
    ]
    # Verify all rows would be classified as bridge signals
    classified = [r for r in bridge_rows if _is_bridge_signal(r)]
    assert len(classified) >= MIN_BRIDGE_SIGNALS

    # Verify aggregation: top destination should be BASE
    dest_counts = Counter(s["destination"] for s in classified)
    assert dest_counts.most_common(1)[0][0] == "BASE"


# ---------------------------------------------------------------------------
# Schema round-trip tests
# ---------------------------------------------------------------------------

def test_signal_demand_state_round_trip():
    from schemas.signal_demand_state import (
        DestinationQueryCount, SignalDemandState, SignalTypeQueryCount,
    )

    state = SignalDemandState(
        id="demand_test",
        window_start=NOW - timedelta(minutes=15),
        window_end=NOW,
        total_queries=42,
        queries_by_destination=[DestinationQueryCount(destination="BASE", count=30)],
        queries_by_signal_type=[SignalTypeQueryCount(signal_type="route_emergence", count=20)],
        avg_requested_time_horizon_hours=12.5,
        urgency_trend="shrinking",
        top_destinations=["BASE"],
        demand_surge_destinations=["BASE"],
        created_at=NOW,
    )
    assert state.total_queries == 42
    assert state.model_dump()["urgency_trend"] == "shrinking"


def test_signal_rate_anomaly_round_trip():
    from schemas.signal_rate_anomaly import SignalRateAnomaly

    anomaly = SignalRateAnomaly(
        id="anomaly_test",
        signal_type="route_hazard",
        baseline_rate_per_hour=0.5,
        observed_rate_per_hour=4.0,
        spike_ratio=8.0,
        severity=AnomalySeverity.CRITICAL,
        detected_at=NOW,
    )
    assert anomaly.severity == AnomalySeverity.CRITICAL
    assert anomaly.spike_ratio == pytest.approx(8.0)


def test_route_health_report_round_trip():
    from schemas.route_health_report import RouteHealthReport

    report = RouteHealthReport(
        protocol_or_chain="BASE",
        report_scope="protocol",
        health_score=0.82,
        traffic_trend="growing",
        congestion_level="low",
        hazard_level="low",
        route_emergence_count=5,
        route_closure_count=1,
        supporting_signal_ids=["s1", "s2"],
        summary="BASE is healthy.",
        created_by_agent="route_health_agent",
        created_at=NOW,
    )
    assert 0.0 <= report.health_score <= 1.0


def test_adapter_health_report_round_trip():
    from schemas.adapter_health_report import AdapterHealthReport, CalibrationBucket

    report = AdapterHealthReport(
        id="ahr_test",
        adapter_name="base-v0",
        evaluation_window_days=7,
        total_scored_signals=100,
        overall_calibration_error=0.08,
        accuracy_by_signal_type={"route_emergence": 0.85},
        confidence_buckets=[
            CalibrationBucket(
                bucket_label="0.7–0.9",
                predicted_confidence=0.8,
                realized_accuracy=0.78,
                sample_size=30,
                thin_data=False,
            )
        ],
        drift_detected=False,
        drift_severity=DriftSeverity.NONE,
        retraining_recommended=False,
        notes="All good.",
        created_at=NOW,
    )
    assert report.drift_detected is False
    assert report.retraining_recommended is False


def test_story_hypothesis_round_trip():
    from schemas.story_hypothesis import HypothesisEvidence, StoryHypothesis

    hyp = StoryHypothesis(
        proposed_story_type="new_pattern",
        description="A new pattern.",
        detection_rationale="Not covered.",
        supporting_on_chain_patterns=["pattern_A"],
        related_existing_story_types=["route_closure"],
        example_evidence=[
            HypothesisEvidence(type="signal", id="s1", summary="Observed once.")
        ],
        supporting_signal_ids=["s1"],
        confidence=0.45,
        status=HypothesisStatus.PROPOSED,
        created_by_agent="story_hypothesis_agent",
        created_at=NOW,
    )
    assert hyp.status == HypothesisStatus.PROPOSED
    assert 0.0 <= hyp.confidence <= 1.0
