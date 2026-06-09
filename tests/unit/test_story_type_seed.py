from __future__ import annotations

import json
from datetime import UTC, datetime

from db.seed_story_types import STORY_TYPE_DEFINITIONS, StoryTypeSeeder


def test_story_type_seeder_deletes_existing_rows_then_inserts_fresh_rows():
    calls = []

    def request_executor(body: bytes) -> bytes:
        calls.append(body.decode("utf-8"))
        return b""

    seeder = StoryTypeSeeder(request_executor=request_executor)

    inserted = seeder.seed(now=datetime(2026, 6, 8, 12, 30, tzinfo=UTC))

    assert inserted == len(STORY_TYPE_DEFINITIONS)
    assert calls[0].startswith("ALTER TABLE StoryTypeDefinitions DELETE WHERE story_type IN")
    assert "mutations_sync = 1" in calls[0]
    assert calls[1].startswith("INSERT INTO StoryTypeDefinitions FORMAT JSONEachRow")
    lines = calls[1].strip().splitlines()
    assert len(lines) == len(STORY_TYPE_DEFINITIONS) + 1
    inserted_row = json.loads(lines[1])
    assert inserted_row["story_type"] == STORY_TYPE_DEFINITIONS[0]["story_type"]
    assert inserted_row["schema_version"] == "1.0"
    assert inserted_row["updated_at"] == "2026-06-08 12:30:00"
