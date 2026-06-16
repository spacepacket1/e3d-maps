from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from urllib.request import Request

import jobs.generate_maps_news as generate_maps_news_job
from clients.clickhouse_client import ClickHouseClient
from clients.qwen_client import QwenClient
from jobs.assemble_cross_chain_activity import run as run_cross_chain_job
from jobs.compute_signal_utility_scores import ClickHouseReadClient
from jobs.generate_maps_news import run as run_maps_news_job
from tests.unit.payloads import (
    cross_chain_activity_state_payload,
    maps_news_brief_payload,
    navigation_signal_payload,
    traffic_state_payload,
)


class StubReadClient(ClickHouseReadClient):
    def __init__(self, rows_by_match: list[tuple[str, list[dict]]]) -> None:
        super().__init__(request_executor=self._request_executor)
        self.rows_by_match = rows_by_match
        self.seen_queries: list[str] = []

    def _request_executor(self, request: Request, timeout: float) -> bytes:
        sql = request.data.decode("utf-8")
        self.seen_queries.append(sql)
        for pattern, rows in self.rows_by_match:
            if pattern in sql:
                payload = "\n".join(json.dumps(row) for row in rows)
                return payload.encode("utf-8")
        return b""


class StubQwenClient(QwenClient):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(request_executor=lambda request, timeout: b"")
        self._responses = list(responses)

    def generate(self, **kwargs) -> str:
        return self._responses.pop(0)


def _signal_row(**overrides) -> dict:
    return navigation_signal_payload(
        id=overrides.pop("id", "navsig_01"),
        signal_type=overrides.pop("signal_type", "route_emergence"),
        answer=overrides.pop(
            "answer",
            "Ethereum-to-Base bridge demand remains active with moderate congestion risk.",
        ),
        origin=overrides.pop("origin", "ETH_DEFI"),
        destination=overrides.pop("destination", "BASE"),
        confidence=overrides.pop("confidence", 0.82),
        risk_level=overrides.pop("risk_level", "medium"),
        created_at=overrides.pop("created_at", "2026-06-16T11:30:00Z"),
        **overrides,
    )


def test_assemble_cross_chain_activity_uses_bounded_window_and_dry_run_writer():
    reader = StubReadClient(
        [
            ("FROM NavigationSignals", [_signal_row()]),
            ("FROM TrafficStates", [traffic_state_payload(created_at="2026-06-16T11:45:00Z")]),
        ]
    )
    output = io.StringIO()
    writer = ClickHouseClient(dry_run=True, output=output)

    state = run_cross_chain_job(
        now=datetime(2026, 6, 16, 12, 0, tzinfo=UTC).replace(tzinfo=None),
        dry_run=True,
        reader=reader,
        writer=writer,
    )

    query = next(sql for sql in reader.seen_queries if "FROM NavigationSignals" in sql)
    assert "created_at >= '2026-06-15 12:00:00'" in query
    assert "ORDER BY created_at DESC" in query
    assert "LIMIT 200" in query
    assert state.market_bias == "transitioning"

    printed = json.loads(output.getvalue())
    assert printed["table"] == "CrossChainActivityStates"
    assert "market_bias" in printed["rows"][0]
    assert "top_routes_json" in printed["rows"][0]


def test_generate_maps_news_uses_bounded_signal_window_and_writes_brief():
    reader = StubReadClient(
        [
            ("FROM TrafficStates", [traffic_state_payload(created_at="2026-06-16T11:55:00Z")]),
            (
                "FROM CrossChainActivityStates",
                [cross_chain_activity_state_payload(created_at="2026-06-16T11:56:00Z")],
            ),
            ("FROM MapsNewsBriefs", [maps_news_brief_payload(created_at="2026-06-16T08:00:00Z")]),
            (
                "FROM NavigationSignals",
                [
                    _signal_row(id="navsig_01", confidence=0.91),
                    _signal_row(
                        id="navsig_02",
                        signal_type="route_hazard",
                        destination="BINANCE",
                        confidence=0.88,
                        risk_level="high",
                        answer="Binance-linked exits are showing elevated hazard signals.",
                    ),
                ],
            ),
        ]
    )
    output = io.StringIO()
    writer = ClickHouseClient(dry_run=True, output=output)
    qwen_client = StubQwenClient(
        [
            json.dumps(
                {
                    "headline": "Ethereum routes stay active while Binance-linked exits carry more risk",
                    "summary": (
                        "The strongest current signals still point to live Ethereum-linked route demand, "
                        "but fresh hazard evidence around Binance-linked exits is keeping the near-term "
                        "read selective rather than broadly risk-on."
                    ),
                    "stance": "cautious",
                    "tags": ["ethereum", "binance", "hazards_active"],
                    "supporting_signal_ids": ["navsig_01", "navsig_02"],
                    "supporting_story_ids": ["story_123"],
                    "supporting_thesis_ids": ["thesis_789"],
                }
            )
        ]
    )

    result = run_maps_news_job(
        now=datetime(2026, 6, 16, 12, 0, tzinfo=UTC).replace(tzinfo=None),
        dry_run=True,
        reader=reader,
        writer=writer,
        qwen_client=qwen_client,
    )

    query = next(sql for sql in reader.seen_queries if "FROM NavigationSignals" in sql)
    assert "created_at >= '2026-06-16 00:00:00'" in query
    assert "ORDER BY confidence DESC, created_at DESC" in query
    assert "LIMIT 50" in query
    assert result.used_fallback is False

    printed = json.loads(output.getvalue())
    assert printed["table"] == "MapsNewsBriefs"
    assert printed["rows"][0]["headline"].startswith("Ethereum routes stay active")
    assert "stance" in printed["rows"][0]


def test_generate_maps_news_unloads_adapter_after_run(monkeypatch):
    reader = StubReadClient(
        [
            ("FROM TrafficStates", [traffic_state_payload(created_at="2026-06-16T11:55:00Z")]),
            (
                "FROM CrossChainActivityStates",
                [cross_chain_activity_state_payload(created_at="2026-06-16T11:56:00Z")],
            ),
            ("FROM MapsNewsBriefs", [maps_news_brief_payload(created_at="2026-06-16T08:00:00Z")]),
            ("FROM NavigationSignals", [_signal_row(id="navsig_01", confidence=0.91)]),
        ]
    )
    writer = ClickHouseClient(dry_run=True, output=io.StringIO())
    qwen_client = StubQwenClient(
        [
            json.dumps(
                {
                    "headline": "Ethereum routes stay active while bridge conditions tighten modestly",
                    "summary": (
                        "The latest route map still favors Ethereum-linked corridors, but fresher "
                        "cross-chain signals suggest execution quality is becoming more selective "
                        "around the busiest bridge paths."
                    ),
                    "stance": "cautious",
                    "tags": ["ethereum", "bridges", "caution"],
                    "supporting_signal_ids": ["navsig_01"],
                    "supporting_story_ids": [],
                    "supporting_thesis_ids": [],
                }
            )
        ]
    )

    events: list[str] = []

    class StubAdapterManager:
        def load(self):
            events.append("load")
            return type("AdapterState", (), {"name": "base-v0", "path": None})()

        def unload(self):
            events.append("unload")
            return None

    monkeypatch.setattr(
        generate_maps_news_job.AdapterManager,
        "from_settings",
        classmethod(lambda cls, settings: StubAdapterManager()),
    )

    run_maps_news_job(
        now=datetime(2026, 6, 16, 12, 0, tzinfo=UTC).replace(tzinfo=None),
        dry_run=False,
        reader=reader,
        writer=writer,
        qwen_client=qwen_client,
    )

    assert events == ["load", "unload"]
