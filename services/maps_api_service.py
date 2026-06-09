from __future__ import annotations

import json
from base64 import b64encode
from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from api.normalizers import (
    normalize_navigation_signal_row,
    normalize_route_prediction_row,
    normalize_story_type_definition_row,
    normalize_traffic_state_row,
)
from clients.clickhouse_client import ClickHouseClientError
from schemas.navigation_signal import NavigationSignal
from schemas.route_prediction import RoutePrediction
from schemas.story_type_definition import StoryTypeDefinition
from schemas.traffic_state import TrafficState

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
    ) -> None:
        self.host = host
        self.port = port
        self.database = database
        self.username = username
        self.password = password
        self.secure = secure
        self.timeout = timeout
        self._query_executor = query_executor or self._default_query_executor

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

    def list_routes(self, *, limit: int = 50, offset: int = 0) -> PaginatedResult[RoutePrediction]:
        return self._list_rows(
            table_sql="""
            SELECT *
            FROM RoutePredictions
            {where_clause}
            ORDER BY created_at DESC, id DESC
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
