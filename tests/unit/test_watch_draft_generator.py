from __future__ import annotations

import json
from datetime import UTC, datetime

from agents.watch_draft_generator import WatchDraftGenerator
from clients.qwen_client import QwenClient, QwenClientError
from schemas.shared_enums import DraftStatus
from schemas.watch_prediction import WatchPrediction


class StubQwenClient(QwenClient):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(request_executor=lambda request, timeout: b"")
        self._responses = list(responses)

    def generate(self, **kwargs) -> str:
        return self._responses.pop(0)


class FailingQwenClient(QwenClient):
    def __init__(self) -> None:
        super().__init__(request_executor=lambda request, timeout: b"")

    def generate(self, **kwargs) -> str:
        raise QwenClientError("model down")


NOW = datetime(2026, 6, 8, 0, 0, tzinfo=UTC)

TRACK_RECORD = {"overall": {"hit_rate": 0.71, "total_scored": 240, "mean_accuracy": 0.69}}


def _prediction(**overrides) -> WatchPrediction:
    payload = {
        "id": "watchpred_abc123",
        "source_signal_id": "navsig_01J",
        "signal_type": "capital_migration",
        "asset_scope": ["ETH"],
        "chain_scope": ["ethereum"],
        "claim": "ETH continues to flow into Coinbase, building sell-side liquidity over 24 hours.",
        "probability": 0.71,
        "realized_direction_expected": "inflow",
        "magnitude_expected": "high",
        "evaluation_window_hours": 24,
        "model": "gpt-4o",
        "adapter": "base-v0",
        "schema_version": "watch_v1",
        "idempotency_key": "abc123def456",
        "created_at": "2026-06-08T00:00:00Z",
    }
    payload.update(overrides)
    return WatchPrediction.model_validate(payload)


VALID_MODEL_JSON = json.dumps(
    {
        "headline": "Sell-side liquidity builds on Coinbase as ETH inflows accelerate",
        "analysis": "Maps flagged a large ETH transfer into Coinbase, a classic precursor to sell pressure.",
        "significance": "Treasury and trading agents routing ETH should weight rising execution risk.",
        "linkedin_draft": " ".join(["navigation"] * 200),
    }
)


def test_valid_model_draft_leads_with_record_and_bounds_lengths():
    gen = WatchDraftGenerator(qwen_client=StubQwenClient([VALID_MODEL_JSON]), model_name="gpt-4o")

    result = gen.generate(_prediction(), track_record=TRACK_RECORD, now=NOW)

    assert result.used_fallback is False
    draft = result.draft
    # X post leads with the track record and respects the 280-char limit.
    assert draft.x_post.startswith("E3D Maps: 71% hit rate (n=240).")
    assert len(draft.x_post) <= 280
    assert draft.headline.startswith("Sell-side liquidity")
    assert len(draft.linkedin_draft.split()) >= 150
    assert draft.status == DraftStatus.DRAFT
    assert draft.track_record_snapshot == TRACK_RECORD
    assert draft.watch_prediction_id == "watchpred_abc123"


def test_routing_object_is_populated():
    gen = WatchDraftGenerator(qwen_client=StubQwenClient([VALID_MODEL_JSON]))

    draft = gen.generate(_prediction(), track_record=TRACK_RECORD, now=NOW).draft

    routing = draft.routing
    assert routing["origin"] == "ethereum"
    assert routing["destination"] == "ETH"
    assert routing["route_type"] == "capital_migration"
    assert routing["expected_direction"] == "inflow"
    assert routing["expected_magnitude"] == "high"
    assert routing["window_hours"] == 24
    assert routing["watch_prediction_id"] == "watchpred_abc123"


def test_x_post_truncates_long_claim_gracefully():
    long_claim = "ETH flows into Coinbase " * 40  # ~960 chars
    gen = WatchDraftGenerator(qwen_client=StubQwenClient([VALID_MODEL_JSON]))

    draft = gen.generate(
        _prediction(claim=long_claim.strip()),
        track_record=TRACK_RECORD,
        now=NOW,
    ).draft

    assert len(draft.x_post) <= 280
    assert draft.x_post.startswith("E3D Maps: 71% hit rate (n=240).")
    assert draft.x_post.endswith("Every transaction is traffic. maps.e3d.ai #E3D")


def test_generic_lead_when_no_track_record():
    gen = WatchDraftGenerator(qwen_client=StubQwenClient([VALID_MODEL_JSON]))

    draft = gen.generate(_prediction(), track_record={}, now=NOW).draft

    assert draft.x_post.startswith("E3D Maps navigation intelligence.")
    assert len(draft.x_post) <= 280


def test_invalid_model_output_falls_back_deterministically():
    gen = WatchDraftGenerator(qwen_client=StubQwenClient(["not json at all"]))

    result = gen.generate(_prediction(), track_record=TRACK_RECORD, now=NOW)

    assert result.used_fallback is True
    draft = result.draft
    assert draft.headline  # non-empty
    assert len(draft.linkedin_draft.split()) >= 150  # schema floor satisfied by fallback
    assert draft.x_post.startswith("E3D Maps: 71% hit rate (n=240).")
    assert draft.status == DraftStatus.DRAFT


def test_short_linkedin_from_model_triggers_fallback():
    short = json.dumps(
        {
            "headline": "ETH inflows accelerate",
            "analysis": "Inflows building.",
            "significance": "Watch execution risk.",
            "linkedin_draft": "Too short to publish.",
        }
    )
    gen = WatchDraftGenerator(qwen_client=StubQwenClient([short]))

    result = gen.generate(_prediction(), track_record=TRACK_RECORD, now=NOW)

    assert result.used_fallback is True
    assert len(result.draft.linkedin_draft.split()) >= 150


def test_model_outage_falls_back_without_crashing():
    gen = WatchDraftGenerator(qwen_client=FailingQwenClient())

    result = gen.generate(_prediction(), track_record=TRACK_RECORD, now=NOW)

    assert result.used_fallback is True
    assert result.draft.headline


def test_track_record_fetched_via_feed_client_when_not_passed():
    class FakeFeed:
        def get_calibration(self, *, source: str):
            assert source == "watch_agent"
            return {"overall": {"hit_rate": 0.5, "total_scored": 10}}

    gen = WatchDraftGenerator(qwen_client=StubQwenClient([VALID_MODEL_JSON]), feed_client=FakeFeed())

    draft = gen.generate(_prediction(), now=NOW).draft

    assert draft.x_post.startswith("E3D Maps: 50% hit rate (n=10).")
    assert draft.track_record_snapshot["overall"]["total_scored"] == 10
