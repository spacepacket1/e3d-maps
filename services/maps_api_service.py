from __future__ import annotations

import json
from base64 import b64encode
from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from api.normalizers import (
    normalize_cross_chain_activity_state_row,
    normalize_maps_news_brief_row,
    normalize_navigation_signal_row,
    normalize_route_prediction_row,
    normalize_story_type_definition_row,
    normalize_traffic_state_row,
    normalize_watch_draft_row,
    normalize_watch_prediction_row,
)
from schemas.consumer_attestation import ConsumerAttestation
from schemas.cross_chain_activity_state import CrossChainActivityState
from schemas.maps_news_brief import MapsNewsBrief
from clients.clickhouse_client import ClickHouseClient, ClickHouseClientError
from schemas.navigation_signal import NavigationSignal
from schemas.recommendation import Recommendation
from schemas.route_prediction import RoutePrediction
from schemas.story_type_definition import StoryTypeDefinition
from schemas.traffic_state import TrafficState
from schemas.watch_draft import WatchDraft
from schemas.watch_prediction import WatchPrediction
from services.recommendation_engine import STORY_TYPE_SIGNAL_TYPES, synthesize_recommendations

T = TypeVar("T")


@dataclass(frozen=True)
class PaginatedResult(Generic[T]):
    items: tuple[T, ...]
    limit: int
    offset: int
    has_more: bool


class MapsAPIService:
    def __init__(
        self,
        *,
        host: str = "localhost",
        port: int = 8123,
        database: str = "default",
        username: str = "default",
        password: str = "",
        secure: bool = False,
        timeout: float = 10.0,
        query_executor: Callable[[bytes], bytes] | None = None,
        clickhouse_writer: ClickHouseClient | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.database = database
        self.username = username
        self.password = password
        self.secure = secure
        self.timeout = timeout
        self._query_executor = query_executor or self._default_query_executor
        self._clickhouse_writer = clickhouse_writer

    def get_latest_state(self) -> TrafficState | None:
        rows = self._query_rows(
            """
            SELECT *
            FROM TrafficStates
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            FORMAT JSONEachRow
            """
        )
        if not rows:
            return None
        return normalize_traffic_state_row(rows[0])

    def get_latest_maps_news_brief(self) -> MapsNewsBrief | None:
        rows = self._query_rows(
            """
            SELECT *
            FROM MapsNewsBriefs
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            FORMAT JSONEachRow
            """
        )
        if not rows:
            return None
        return normalize_maps_news_brief_row(rows[0])

    def list_maps_news_briefs(self, *, limit: int = 5, offset: int = 0) -> PaginatedResult[MapsNewsBrief]:
        return self._list_rows(
            table_sql="""
            SELECT *
            FROM MapsNewsBriefs
            ORDER BY created_at DESC, id DESC
            {limit_clause}
            FORMAT JSONEachRow
            """,
            filters=[],
            limit=limit,
            offset=offset,
            normalizer=normalize_maps_news_brief_row,
        )

    def get_latest_cross_chain_activity_state(self) -> CrossChainActivityState | None:
        rows = self._query_rows(
            """
            SELECT *
            FROM CrossChainActivityStates
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            FORMAT JSONEachRow
            """
        )
        if not rows:
            return None
        return normalize_cross_chain_activity_state_row(rows[0])

    def list_signals(
        self,
        *,
        signal_type: str | None = None,
        asset: str | None = None,
        chain: str | None = None,
        time_horizon_hours: int | None = None,
        min_confidence: float | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> PaginatedResult[NavigationSignal]:
        filters = []
        if signal_type:
            filters.append(f"signal_type = {self._sql_string(signal_type)}")
        if asset:
            filters.append(f"has(asset_scope, {self._sql_string(asset)})")
        if chain:
            filters.append(f"has(chain_scope, {self._sql_string(chain)})")
        if time_horizon_hours is not None:
            filters.append(f"time_horizon_hours = {self._sql_uint(time_horizon_hours)}")
        if min_confidence is not None:
            filters.append(f"confidence >= {self._sql_float(min_confidence)}")

        return self._list_rows(
            table_sql="""
            SELECT *
            FROM NavigationSignals
            {where_clause}
            ORDER BY created_at DESC, id DESC
            LIMIT 1 BY signal_type, destination
            {limit_clause}
            FORMAT JSONEachRow
            """,
            filters=filters,
            limit=limit,
            offset=offset,
            normalizer=normalize_navigation_signal_row,
        )

    def get_signal(self, signal_id: str) -> NavigationSignal | None:
        rows = self._query_rows(
            f"""
            SELECT *
            FROM NavigationSignals
            WHERE id = {self._sql_string(signal_id)}
            ORDER BY created_at DESC
            LIMIT 1
            FORMAT JSONEachRow
            """
        )
        if not rows:
            return None
        return normalize_navigation_signal_row(rows[0])

    def ingest_consumer_attestation(
        self,
        payload: ConsumerAttestation | dict[str, Any],
    ) -> ConsumerAttestation:
        """Validate and persist a downstream consumer's attestation.

        This is the producer-side ingestion path that feeds
        ``PredictionOutcome.consumer_exposure`` at settlement. The public
        ``POST /api/maps/outcomes`` endpoint in the main e3d server is a
        documented cross-repo step; this method defines and tests the contract.
        """
        attestation = (
            payload
            if isinstance(payload, ConsumerAttestation)
            else ConsumerAttestation.model_validate(payload)
        )
        self._writer().insert_consumer_attestation(attestation)
        return attestation

    def _writer(self) -> ClickHouseClient:
        if self._clickhouse_writer is None:
            self._clickhouse_writer = ClickHouseClient(
                host=self.host,
                port=self.port,
                database=self.database,
                username=self.username,
                password=self.password,
                secure=self.secure,
                timeout=self.timeout,
            )
        return self._clickhouse_writer

    def get_notable_signals(
        self,
        *,
        min_score: int = 0,
        since: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> PaginatedResult[dict[str, Any]]:
        """Return recent navigation signals joined to their latest utility score,
        ranked by a server-side ``notability`` score.

        ``notability = round(100 * final_signal_utility_score)`` when a utility
        score exists, otherwise ``round(100 * confidence)``. Clients only
        threshold-filter via ``min_score``.
        """
        bounded_limit = self._normalize_limit(limit)
        bounded_offset = self._normalize_offset(offset)

        filters = [f"notability >= {max(0, int(min_score))}"]
        if since:
            filters.append(f"created_at > {self._sql_string(since)}")
        where_clause = "WHERE " + " AND ".join(filters)

        sql = f"""
        SELECT *
        FROM
        (
            SELECT
                ns.id           AS signal_id,
                ns.signal_type  AS signal_type,
                ns.asset_scope  AS asset_scope,
                ns.chain_scope  AS chain_scope,
                ns.confidence   AS confidence,
                ns.question     AS question,
                ns.answer       AS answer,
                ns.created_at   AS created_at,
                round(100 * if(sus.score_count > 0, sus.utility, ns.confidence)) AS notability
            FROM NavigationSignals ns
            LEFT JOIN
            (
                SELECT
                    navigation_signal_id,
                    argMax(final_signal_utility_score, created_at) AS utility,
                    count() AS score_count
                FROM SignalUtilityScores
                GROUP BY navigation_signal_id
            ) sus ON sus.navigation_signal_id = ns.id
        )
        {where_clause}
        ORDER BY notability DESC, created_at DESC, signal_id DESC
        LIMIT {bounded_limit + 1} OFFSET {bounded_offset}
        FORMAT JSONEachRow
        """
        rows = self._query_rows(sql)
        has_more = len(rows) > bounded_limit
        items = tuple(_normalize_notable_row(row) for row in rows[:bounded_limit])
        return PaginatedResult(
            items=items,
            limit=bounded_limit,
            offset=bounded_offset,
            has_more=has_more,
        )

    def list_routes(self, *, limit: int = 50, offset: int = 0) -> PaginatedResult[RoutePrediction]:
        return self._list_rows(
            table_sql="""
            SELECT *
            FROM RoutePredictions
            {where_clause}
            ORDER BY created_at DESC, id DESC
            LIMIT 1 BY route_type, destination
            {limit_clause}
            FORMAT JSONEachRow
            """,
            filters=[],
            limit=limit,
            offset=offset,
            normalizer=normalize_route_prediction_row,
        )

    def list_hazards(self, *, limit: int = 50, offset: int = 0) -> PaginatedResult[NavigationSignal]:
        return self._list_rows(
            table_sql="""
            SELECT *
            FROM NavigationSignals
            {where_clause}
            ORDER BY created_at DESC, id DESC
            LIMIT 1 BY signal_type, destination
            {limit_clause}
            FORMAT JSONEachRow
            """,
            filters=[
                "signal_type IN ('route_hazard', 'route_closure')",
            ],
            limit=limit,
            offset=offset,
            normalizer=normalize_navigation_signal_row,
        )

    def list_predictions(self, *, limit: int = 50, offset: int = 0) -> PaginatedResult[NavigationSignal]:
        return self._list_rows(
            table_sql="""
            SELECT *
            FROM NavigationSignals
            {where_clause}
            ORDER BY created_at DESC, id DESC
            LIMIT 1 BY signal_type, destination
            {limit_clause}
            FORMAT JSONEachRow
            """,
            filters=[
                "signal_type IN ('capital_migration', 'destination_prediction')",
            ],
            limit=limit,
            offset=offset,
            normalizer=normalize_navigation_signal_row,
        )

    def list_destinations(self, *, limit: int = 50, offset: int = 0) -> PaginatedResult[NavigationSignal]:
        return self._list_rows(
            table_sql="""
            SELECT *
            FROM NavigationSignals
            {where_clause}
            ORDER BY confidence DESC, created_at DESC, id DESC
            LIMIT 1 BY destination
            {limit_clause}
            FORMAT JSONEachRow
            """,
            filters=[
                "signal_type = 'destination_prediction'",
            ],
            limit=limit,
            offset=offset,
            normalizer=normalize_navigation_signal_row,
        )

    def list_congestion(self, *, limit: int = 50, offset: int = 0) -> PaginatedResult[NavigationSignal]:
        return self._list_rows(
            table_sql="""
            SELECT *
            FROM NavigationSignals
            {where_clause}
            ORDER BY created_at DESC, id DESC
            LIMIT 1 BY destination
            {limit_clause}
            FORMAT JSONEachRow
            """,
            filters=[
                "signal_type = 'congestion_formation'",
            ],
            limit=limit,
            offset=offset,
            normalizer=normalize_navigation_signal_row,
        )

    def get_latest_flow_graph(self) -> dict[str, Any] | None:
        snapshot_rows = self._query_rows(
            """
            SELECT *
            FROM FlowGraphSnapshots
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            FORMAT JSONEachRow
            """
        )
        if not snapshot_rows:
            return None
        snapshot = snapshot_rows[0]
        snapshot_id = snapshot["id"]

        edge_rows = self._query_rows(
            f"""
            SELECT *
            FROM FlowGraphEdges
            WHERE snapshot_id = {self._sql_string(snapshot_id)}
            ORDER BY origin ASC, destination ASC
            FORMAT JSONEachRow
            """
        )
        return _build_graph_response(snapshot, edge_rows)

    def get_flow_graph_around(self, node: str) -> dict[str, Any]:
        snapshot_rows = self._query_rows(
            """
            SELECT id, created_at
            FROM FlowGraphSnapshots
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            FORMAT JSONEachRow
            """
        )
        if not snapshot_rows:
            return _empty_subgraph(node)
        snapshot_id = snapshot_rows[0]["id"]
        snapshot_created_at = snapshot_rows[0]["created_at"]

        edge_rows = self._query_rows(
            f"""
            SELECT *
            FROM FlowGraphEdges
            WHERE snapshot_id = {self._sql_string(snapshot_id)}
              AND (origin = {self._sql_string(node)} OR destination = {self._sql_string(node)})
            ORDER BY origin ASC, destination ASC
            FORMAT JSONEachRow
            """
        )
        return _build_subgraph_response(node, snapshot_id, snapshot_created_at, edge_rows)

    def get_calibration(self, *, lookback_days: int = 30) -> dict[str, Any]:
        """Return reliability-curve and utility data for the calibration endpoint.

        Three queries:
        1. Overall accuracy / hit-rate summary.
        2. Per (signal_type, confidence_bucket) reliability curve points.
        3. Per signal_type utility-score distribution from SignalUtilityScores.
        """
        lookback_clause = (
            f"po.created_at >= now() - INTERVAL {max(1, int(lookback_days))} DAY"
        )

        overall_rows = self._query_rows(
            f"""
            SELECT
                avg(po.prediction_accuracy)         AS mean_accuracy,
                avg(ns.confidence)                  AS mean_confidence,
                countIf(po.map_prediction_correct = 1) AS correct_count,
                count()                             AS total_count
            FROM PredictionOutcomes po
            INNER JOIN NavigationSignals ns ON ns.id = po.navigation_signal_id
            WHERE {lookback_clause}
            FORMAT JSONEachRow
            """
        )

        curve_rows = self._query_rows(
            f"""
            SELECT
                ns.signal_type                              AS signal_type,
                floor(ns.confidence * 10) / 10             AS confidence_bucket,
                avg(ns.confidence)                         AS mean_confidence,
                avg(po.prediction_accuracy)                AS realized_accuracy,
                count()                                    AS sample_count
            FROM PredictionOutcomes po
            INNER JOIN NavigationSignals ns ON ns.id = po.navigation_signal_id
            WHERE {lookback_clause}
            GROUP BY signal_type, confidence_bucket
            ORDER BY signal_type ASC, confidence_bucket ASC
            FORMAT JSONEachRow
            """
        )

        utility_rows = self._query_rows(
            """
            SELECT
                ns.signal_type                             AS signal_type,
                avg(sus.final_signal_utility_score)        AS mean_utility,
                min(sus.final_signal_utility_score)        AS min_utility,
                max(sus.final_signal_utility_score)        AS max_utility,
                count()                                    AS sample_count
            FROM SignalUtilityScores sus
            INNER JOIN NavigationSignals ns ON ns.id = sus.navigation_signal_id
            GROUP BY signal_type
            FORMAT JSONEachRow
            """
        )

        # Build overall summary.
        overall: dict[str, Any] = {
            "mean_confidence": None,
            "mean_accuracy": None,
            "calibration_error": None,
            "hit_rate": None,
            "total_scored": 0,
        }
        if overall_rows:
            row = overall_rows[0]
            total = int(row.get("total_count") or 0)
            mean_acc = float(row.get("mean_accuracy") or 0.0) if total else None
            mean_conf = float(row.get("mean_confidence") or 0.0) if total else None
            correct = int(row.get("correct_count") or 0)
            overall = {
                "mean_confidence": round(mean_conf, 4) if mean_conf is not None else None,
                "mean_accuracy": round(mean_acc, 4) if mean_acc is not None else None,
                "calibration_error": (
                    round(abs(mean_acc - mean_conf), 4)
                    if mean_acc is not None and mean_conf is not None
                    else None
                ),
                "hit_rate": round(correct / total, 4) if total else None,
                "total_scored": total,
            }

        # Group reliability curve points by signal_type.
        by_type: dict[str, dict[str, Any]] = {}
        for row in curve_rows:
            st = row.get("signal_type") or "unknown"
            if st not in by_type:
                by_type[st] = {"reliability_curve": [], "utility": None}
            by_type[st]["reliability_curve"].append(
                {
                    "confidence_bucket": round(float(row.get("confidence_bucket") or 0), 1),
                    "mean_confidence": round(float(row.get("mean_confidence") or 0), 4),
                    "realized_accuracy": round(float(row.get("realized_accuracy") or 0), 4),
                    "sample_count": int(row.get("sample_count") or 0),
                }
            )

        # Merge utility stats.
        for row in utility_rows:
            st = row.get("signal_type") or "unknown"
            if st not in by_type:
                by_type[st] = {"reliability_curve": [], "utility": None}
            by_type[st]["utility"] = {
                "mean": round(float(row.get("mean_utility") or 0), 4),
                "min": round(float(row.get("min_utility") or 0), 4),
                "max": round(float(row.get("max_utility") or 0), 4),
                "sample_count": int(row.get("sample_count") or 0),
            }

        return {
            "lookback_days": lookback_days,
            "overall": overall,
            "by_signal_type": by_type,
        }

    def list_story_types(self, *, limit: int = 100, offset: int = 0) -> PaginatedResult[StoryTypeDefinition]:
        return self._list_rows(
            table_sql="""
            SELECT *
            FROM
            (
                SELECT *
                FROM StoryTypeDefinitions
                ORDER BY updated_at DESC, story_type ASC
            )
            {where_clause}
            LIMIT 1 BY story_type
            ORDER BY story_type ASC
            {limit_clause}
            FORMAT JSONEachRow
            """,
            filters=[],
            limit=limit,
            offset=offset,
            normalizer=normalize_story_type_definition_row,
        )

    def get_recommendations(
        self,
        *,
        objective: str | None = None,
        asset: str | None = None,
        address: str | None = None,
        story_type: str | None = None,
        max_results: int = 10,
    ) -> list[Recommendation]:
        fetch_limit = max(50, max_results * 5)
        signals_result = self.list_signals(asset=asset, limit=fetch_limit, offset=0)
        signals = list(signals_result.items)

        if story_type:
            allowed = STORY_TYPE_SIGNAL_TYPES.get(story_type.lower())
            if allowed:
                signals = [s for s in signals if s.signal_type in allowed]

        routes_result = self.list_routes(limit=20, offset=0)
        routes = list(routes_result.items)

        bounded = max(1, min(int(max_results), 100))
        return synthesize_recommendations(signals, routes, objective=objective, max_results=bounded)

    def get_story_type(self, story_type: str) -> StoryTypeDefinition | None:
        rows = self._query_rows(
            f"""
            SELECT *
            FROM StoryTypeDefinitions
            WHERE story_type = {self._sql_string(story_type)}
            ORDER BY updated_at DESC
            LIMIT 1
            FORMAT JSONEachRow
            """
        )
        if not rows:
            return None
        return normalize_story_type_definition_row(rows[0])

    def list_watch_drafts(
        self, *, limit: int = 50, offset: int = 0
    ) -> PaginatedResult[WatchDraft]:
        return self._list_rows(
            table_sql="""
            SELECT *
            FROM WatchDrafts
            {where_clause}
            ORDER BY created_at DESC, id DESC
            {limit_clause}
            FORMAT JSONEachRow
            """,
            filters=[],
            limit=limit,
            offset=offset,
            normalizer=normalize_watch_draft_row,
        )

    def get_watch_draft(self, draft_id: str) -> WatchDraft | None:
        rows = self._query_rows(
            f"""
            SELECT *
            FROM WatchDrafts
            WHERE id = {self._sql_string(draft_id)}
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            FORMAT JSONEachRow
            """
        )
        if not rows:
            return None
        return normalize_watch_draft_row(rows[0])

    def get_watch_prediction(self, prediction_id: str) -> WatchPrediction | None:
        rows = self._query_rows(
            f"""
            SELECT *
            FROM WatchPredictions
            WHERE id = {self._sql_string(prediction_id)}
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            FORMAT JSONEachRow
            """
        )
        if not rows:
            return None
        return normalize_watch_prediction_row(rows[0])

    def _list_rows(
        self,
        *,
        table_sql: str,
        filters: list[str],
        limit: int,
        offset: int,
        normalizer: Callable[[dict[str, Any]], T],
    ) -> PaginatedResult[T]:
        bounded_limit = self._normalize_limit(limit)
        bounded_offset = self._normalize_offset(offset)
        where_clause = ""
        if filters:
            where_clause = "WHERE " + " AND ".join(filters)
        limit_clause = f"LIMIT {bounded_limit + 1} OFFSET {bounded_offset}"
        rows = self._query_rows(
            table_sql.format(where_clause=where_clause, limit_clause=limit_clause)
        )
        has_more = len(rows) > bounded_limit
        items = tuple(normalizer(row) for row in rows[:bounded_limit])
        return PaginatedResult(
            items=items,
            limit=bounded_limit,
            offset=bounded_offset,
            has_more=has_more,
        )

    def _query_rows(self, sql: str) -> list[dict[str, Any]]:
        payload = sql.strip().encode("utf-8")
        try:
            raw = self._query_executor(payload)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ClickHouseClientError(
                f"ClickHouse query failed with status {exc.code}: {detail}"
            ) from exc
        except URLError as exc:
            raise ClickHouseClientError(f"ClickHouse query failed: {exc.reason}") from exc

        if not raw.strip():
            return []

        rows = []
        for line in raw.decode("utf-8").splitlines():
            text = line.strip()
            if not text:
                continue
            rows.append(json.loads(text))
        return rows

    def _default_query_executor(self, body: bytes) -> bytes:
        scheme = "https" if self.secure else "http"
        url = f"{scheme}://{self.host}:{self.port}/?database={self.database}"
        headers = {"Content-Type": "text/plain; charset=utf-8"}
        if self.username or self.password:
            token = b64encode(f"{self.username}:{self.password}".encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {token}"

        request = Request(url=url, data=body, headers=headers, method="POST")
        with urlopen(request, timeout=self.timeout) as response:
            return response.read()

    @staticmethod
    def _normalize_limit(limit: int) -> int:
        return max(1, min(int(limit), 200))

    @staticmethod
    def _normalize_offset(offset: int) -> int:
        return max(0, int(offset))

    @staticmethod
    def _sql_string(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"

    @staticmethod
    def _sql_uint(value: int) -> str:
        return str(max(0, int(value)))

    @staticmethod
    def _sql_float(value: float) -> str:
        bounded = max(0.0, min(float(value), 1.0))
        return format(bounded, "g")


def _normalize_notable_row(row: dict[str, Any]) -> dict[str, Any]:
    summary = row.get("answer") or row.get("question") or ""
    return {
        "signal_id": row.get("signal_id") or "",
        "signal_type": row.get("signal_type") or "",
        "asset_scope": list(row.get("asset_scope") or []),
        "chain_scope": list(row.get("chain_scope") or []),
        "confidence": float(row.get("confidence") or 0.0),
        "notability": int(row.get("notability") or 0),
        "created_at": row.get("created_at") or "",
        "summary": summary,
    }


# ── FlowGraph response builders ───────────────────────────────────────────────

def _serialize_edge(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id") or "",
        "origin": row.get("origin") or "",
        "destination": row.get("destination") or "",
        "strength": row.get("strength") or "",
        "confidence": row.get("confidence") or 0.0,
        "hazard_level": row.get("hazard_level") or "low",
        "edge_status": row.get("edge_status") or "active",
        "source_signal_ids": list(row.get("source_signal_ids") or []),
    }


def _build_graph_response(snapshot: dict[str, Any], edge_rows: list[dict[str, Any]]) -> dict[str, Any]:
    edges = [_serialize_edge(r) for r in edge_rows]
    active = [e for e in edges if e["edge_status"] != "closed"]
    nodes = sorted({n for e in active for n in (e["origin"], e["destination"])})
    return {
        "snapshot_id": snapshot.get("id") or "",
        "created_at": snapshot.get("created_at") or "",
        "signal_count": snapshot.get("signal_count") or 0,
        "node_count": snapshot.get("node_count") or 0,
        "edge_count": snapshot.get("edge_count") or 0,
        "nodes": nodes,
        "edges": edges,
    }


def _build_subgraph_response(
    node: str,
    snapshot_id: str,
    snapshot_created_at: str,
    edge_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    edges = [_serialize_edge(r) for r in edge_rows]
    inbound = [e for e in edges if e["destination"] == node and e["edge_status"] != "closed"]
    outbound = [e for e in edges if e["origin"] == node and e["edge_status"] != "closed"]
    nodes = sorted({n for e in inbound + outbound for n in (e["origin"], e["destination"])})
    return {
        "node": node,
        "snapshot_id": snapshot_id,
        "created_at": snapshot_created_at,
        "nodes": nodes,
        "inbound": inbound,
        "outbound": outbound,
        "edges": inbound + outbound,
    }


def _empty_subgraph(node: str) -> dict[str, Any]:
    return {
        "node": node,
        "snapshot_id": None,
        "created_at": None,
        "nodes": [],
        "inbound": [],
        "outbound": [],
        "edges": [],
    }
