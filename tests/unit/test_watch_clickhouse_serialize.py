from __future__ import annotations

import io
import json

from clients.clickhouse_client import ClickHouseClient
from tests.unit.test_watch_schemas import (
    consumer_attestation_payload,
    watch_draft_payload,
    watch_prediction_payload,
)


def test_insert_watch_prediction_serializes_expected_shape():
    output = io.StringIO()
    client = ClickHouseClient(dry_run=True, output=output)

    inserted = client.insert_watch_prediction(watch_prediction_payload())

    assert inserted == 1
    printed = json.loads(output.getvalue())
    assert printed["table"] == "WatchPredictions"
    row = printed["rows"][0]
    assert row["signal_type"] == "capital_migration"
    assert row["realized_direction_expected"] == "inflow"
    assert row["magnitude_expected"] == "high"
    assert row["probability"] == 0.62
    assert row["status"] == "pending"
    assert row["idempotency_key"] == "abc123"
    assert row["created_at"] == "2026-06-08 00:00:00"
    assert row["source_prediction_id"] == ""


def test_insert_watch_draft_serializes_json_columns_as_strings():
    output = io.StringIO()
    client = ClickHouseClient(dry_run=True, output=output)

    inserted = client.insert_watch_draft(
        watch_draft_payload(
            track_record_snapshot={"n": 240, "brier": 0.18},
            routing={"origin": "ETH", "destination": "coinbase"},
        )
    )

    assert inserted == 1
    printed = json.loads(output.getvalue())
    assert printed["table"] == "WatchDrafts"
    row = printed["rows"][0]
    assert json.loads(row["track_record_snapshot"])["n"] == 240
    assert json.loads(row["routing"])["destination"] == "coinbase"
    assert row["status"] == "draft"
    assert len(row["x_post"]) <= 280


def test_insert_consumer_attestation_converts_bool_to_uint8():
    output = io.StringIO()
    client = ClickHouseClient(dry_run=True, output=output)

    inserted = client.insert_consumer_attestation(consumer_attestation_payload())

    assert inserted == 1
    printed = json.loads(output.getvalue())
    assert printed["table"] == "ConsumerAttestations"
    row = printed["rows"][0]
    assert row["acted"] == 1
    assert row["observed_direction"] == "inflow"
    assert row["observed_magnitude"] == "high"


def test_insert_consumer_attestation_blank_observations_when_none():
    output = io.StringIO()
    client = ClickHouseClient(dry_run=True, output=output)

    client.insert_consumer_attestation(
        consumer_attestation_payload(acted=False, observed_direction=None, observed_magnitude=None)
    )

    row = json.loads(output.getvalue())["rows"][0]
    assert row["acted"] == 0
    assert row["observed_direction"] == ""
    assert row["observed_magnitude"] == ""
