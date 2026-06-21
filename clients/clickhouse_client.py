from __future__ import annotations

import json
from base64 import b64encode
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, TextIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

UTC = timezone.utc

from schemas.consumer_attestation import ConsumerAttestation
from schemas.cross_chain_activity_state import CrossChainActivityState
from schemas.flow_graph import FlowEdge, FlowGraphSnapshot
from schemas.maps_news_brief import MapsNewsBrief
from schemas.navigation_signal import NavigationSignal
from schemas.prediction_outcome import PredictionOutcome
from schemas.route_prediction import RoutePrediction
from schemas.shared_enums import OutcomeStatus
from schemas.signal_utility_score import SignalUtilityScore
from schemas.traffic_state import TrafficState
from schemas.watch_draft import WatchDraft
from schemas.watch_prediction import WatchPrediction


class ClickHouseClientError(RuntimeError):
    """Raised when a ClickHouse write fails."""


class ClickHouseClient:
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
        dry_run: bool = False,
        output: TextIO | None = None,
        request_executor=None,
    ) -> None:
        self.host = host
        self.port = port
        self.database = database
        self.username = username
        self.password = password
        self.secure = secure
        self.timeout = timeout
        self.dry_run = dry_run
        self.output = output
        self._request_executor = request_executor or self._default_request_executor

    def recent_signal_exists(
        self,
        signal_type: str,
        origin: str,
        destination: str,
        *,
        within_hours: int = 4,
    ) -> bool:
        """Return True if an identical (type, origin, destination) signal was written within within_hours."""
        if self.dry_run:
            return False
        st = self._sql_string(signal_type)
        og = self._sql_string(origin)
        dst = self._sql_string(destination)
        query = (
            f"SELECT count() AS cnt FROM NavigationSignals "
            f"WHERE signal_type = {st} AND origin = {og} AND destination = {dst} "
            f"AND created_at >= now() - INTERVAL {within_hours} HOUR "
            "FORMAT JSONEachRow"
        )
        body = query.encode("utf-8")
        try:
            raw = self._request_executor(body)
        except (HTTPError, URLError, ClickHouseClientError):
            return False
        for line in raw.decode("utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
                if int(row.get("cnt", 0)) > 0:
                    return True
            except (ValueError, KeyError):
                pass
        return False

    def insert_navigation_signal(self, record: NavigationSignal | dict[str, Any]) -> int:
        return self.insert_navigation_signals([record])

    def insert_navigation_signals(
        self,
        records: Iterable[NavigationSignal | dict[str, Any]],
    ) -> int:
        return self._insert_models(
            table_name="NavigationSignals",
            records=records,
            schema_model=NavigationSignal,
            serializer=self._serialize_navigation_signal,
        )

    def insert_route_prediction(self, record: RoutePrediction | dict[str, Any]) -> int:
        return self.insert_route_predictions([record])

    def insert_route_predictions(
        self,
        records: Iterable[RoutePrediction | dict[str, Any]],
    ) -> int:
        return self._insert_models(
            table_name="RoutePredictions",
            records=records,
            schema_model=RoutePrediction,
            serializer=self._serialize_route_prediction,
        )

    def insert_traffic_state(self, record: TrafficState | dict[str, Any]) -> int:
        return self.insert_traffic_states([record])

    def insert_traffic_states(
        self,
        records: Iterable[TrafficState | dict[str, Any]],
    ) -> int:
        return self._insert_models(
            table_name="TrafficStates",
            records=records,
            schema_model=TrafficState,
            serializer=self._serialize_traffic_state,
        )

    def insert_prediction_outcome(
        self,
        record: PredictionOutcome | dict[str, Any],
    ) -> int:
        return self.insert_prediction_outcomes([record])

    def insert_prediction_outcomes(
        self,
        records: Iterable[PredictionOutcome | dict[str, Any]],
    ) -> int:
        return self._insert_models(
            table_name="PredictionOutcomes",
            records=records,
            schema_model=PredictionOutcome,
            serializer=self._serialize_prediction_outcome,
        )

    def insert_maps_news_brief(self, record: MapsNewsBrief | dict[str, Any]) -> int:
        return self.insert_maps_news_briefs([record])

    def insert_maps_news_briefs(
        self,
        records: Iterable[MapsNewsBrief | dict[str, Any]],
    ) -> int:
        return self._insert_models(
            table_name="MapsNewsBriefs",
            records=records,
            schema_model=MapsNewsBrief,
            serializer=self._serialize_maps_news_brief,
        )

    def insert_watch_prediction(self, record: WatchPrediction | dict[str, Any]) -> int:
        return self.insert_watch_predictions([record])

    def insert_watch_predictions(
        self,
        records: Iterable[WatchPrediction | dict[str, Any]],
    ) -> int:
        return self._insert_models(
            table_name="WatchPredictions",
            records=records,
            schema_model=WatchPrediction,
            serializer=self._serialize_watch_prediction,
        )

    def insert_watch_draft(self, record: WatchDraft | dict[str, Any]) -> int:
        return self.insert_watch_drafts([record])

    def insert_watch_drafts(
        self,
        records: Iterable[WatchDraft | dict[str, Any]],
    ) -> int:
        return self._insert_models(
            table_name="WatchDrafts",
            records=records,
            schema_model=WatchDraft,
            serializer=self._serialize_watch_draft,
        )

    def insert_consumer_attestation(
        self,
        record: ConsumerAttestation | dict[str, Any],
    ) -> int:
        return self.insert_consumer_attestations([record])

    def insert_consumer_attestations(
        self,
        records: Iterable[ConsumerAttestation | dict[str, Any]],
    ) -> int:
        return self._insert_models(
            table_name="ConsumerAttestations",
            records=records,
            schema_model=ConsumerAttestation,
            serializer=self._serialize_consumer_attestation,
        )

    def insert_cross_chain_activity_state(
        self,
        record: CrossChainActivityState | dict[str, Any],
    ) -> int:
        return self.insert_cross_chain_activity_states([record])

    def insert_cross_chain_activity_states(
        self,
        records: Iterable[CrossChainActivityState | dict[str, Any]],
    ) -> int:
        return self._insert_models(
            table_name="CrossChainActivityStates",
            records=records,
            schema_model=CrossChainActivityState,
            serializer=self._serialize_cross_chain_activity_state,
        )

    def insert_signal_utility_score(
        self,
        record: SignalUtilityScore | dict[str, Any],
    ) -> int:
        return self.insert_signal_utility_scores([record])

    def insert_signal_utility_scores(
        self,
        records: Iterable[SignalUtilityScore | dict[str, Any]],
    ) -> int:
        return self._insert_models(
            table_name="SignalUtilityScores",
            records=records,
            schema_model=SignalUtilityScore,
            serializer=self._serialize_signal_utility_score,
        )

    def insert_flow_graph_snapshot(self, record: FlowGraphSnapshot | dict[str, Any]) -> int:
        return self._insert_models(
            table_name="FlowGraphSnapshots",
            records=[record],
            schema_model=FlowGraphSnapshot,
            serializer=self._serialize_flow_graph_snapshot,
        )

    def insert_flow_graph_edges(self, records: Iterable[FlowEdge | dict[str, Any]]) -> int:
        return self._insert_models(
            table_name="FlowGraphEdges",
            records=records,
            schema_model=FlowEdge,
            serializer=self._serialize_flow_edge,
        )

    def update_navigation_signal_outcome_status(
        self,
        navigation_signal_id: str,
        outcome_status: OutcomeStatus | str,
    ) -> int:
        return self.update_navigation_signal_outcome_statuses(
            {navigation_signal_id: outcome_status}
        )

    def update_navigation_signal_outcome_statuses(
        self,
        statuses: dict[str, OutcomeStatus | str],
    ) -> int:
        updates: list[dict[str, str]] = []
        for navigation_signal_id, raw_status in statuses.items():
            if not navigation_signal_id:
                continue
            normalized_status = (
                raw_status.value
                if isinstance(raw_status, OutcomeStatus)
                else OutcomeStatus(str(raw_status)).value
            )
            updates.append(
                {
                    "id": navigation_signal_id,
                    "outcome_status": normalized_status,
                }
            )

        if not updates:
            return 0

        if self.dry_run:
            self._print_dry_run(table_name="NavigationSignalsOutcomeStatus", rows=updates)
            return len(updates)

        for update in updates:
            query = (
                "ALTER TABLE NavigationSignals "
                f"UPDATE outcome_status = {self._sql_string(update['outcome_status'])} "
                f"WHERE id = {self._sql_string(update['id'])}"
            )
            self._request_executor(query.encode("utf-8"))
        return len(updates)

    def select_rows(self, sql: str) -> list[dict[str, Any]]:
        """Execute a SELECT query and return the result as a list of dicts.

        Appends ``FORMAT JSONEachRow`` if not already present.
        """
        normalized = sql.rstrip()
        if "FORMAT " not in normalized.upper():
            normalized += " FORMAT JSONEachRow"
        raw = self._request_executor(normalized.encode("utf-8"))
        rows: list[dict[str, Any]] = []
        for line in raw.decode("utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if stripped:
                try:
                    rows.append(json.loads(stripped))
                except (ValueError, KeyError):
                    pass
        return rows

    def _insert_models(
        self,
        *,
        table_name: str,
        records: Iterable[Any],
        schema_model,
        serializer,
    ) -> int:
        validated_records = []
        for record in records:
            if isinstance(record, schema_model):
                validated_records.append(record)
            else:
                validated_records.append(schema_model.model_validate(record))

        if not validated_records:
            return 0

        rows = [serializer(record) for record in validated_records]
        return self._insert_rows(table_name=table_name, rows=rows)

    def _insert_rows(self, *, table_name: str, rows: list[dict[str, Any]]) -> int:
        if self.dry_run:
            self._print_dry_run(table_name=table_name, rows=rows)
            return len(rows)

        query = f"INSERT INTO {table_name} FORMAT JSONEachRow"
        payload = "\n".join(json.dumps(row, separators=(",", ":"), sort_keys=True) for row in rows)
        body = f"{query}\n{payload}\n".encode("utf-8")
        self._request_executor(body)
        return len(rows)

    def _print_dry_run(self, *, table_name: str, rows: list[dict[str, Any]]) -> None:
        stream = self.output
        text = json.dumps({"table": table_name, "rows": rows}, indent=2, sort_keys=True)
        if stream is None:
            print(text)
            return
        stream.write(text)
        stream.write("\n")

    def _default_request_executor(self, body: bytes) -> bytes:
        scheme = "https" if self.secure else "http"
        url = f"{scheme}://{self.host}:{self.port}/?database={self.database}"
        headers = {"Content-Type": "text/plain; charset=utf-8"}
        if self.username or self.password:
            token = b64encode(f"{self.username}:{self.password}".encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {token}"

        request = Request(url=url, data=body, headers=headers, method="POST")

        try:
            with urlopen(request, timeout=self.timeout) as response:
                return response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ClickHouseClientError(
                f"ClickHouse insert failed with status {exc.code}: {detail}"
            ) from exc
        except URLError as exc:
            raise ClickHouseClientError(f"ClickHouse insert failed: {exc.reason}") from exc

    @staticmethod
    def _serialize_navigation_signal(record: NavigationSignal) -> dict[str, Any]:
        return {
            "id": record.id or "",
            "signal_type": record.signal_type,
            "question": record.question,
            "answer": record.answer,
            "origin": record.origin or "",
            "destination": record.destination or "",
            "asset_scope": record.asset_scope,
            "chain_scope": record.chain_scope,
            "time_horizon_hours": record.time_horizon_hours,
            "confidence": record.confidence,
            "risk_level": record.risk_level.value,
            "signal_strength": record.signal_strength.value if record.signal_strength else "",
            "market_state": record.market_state.value if record.market_state else "",
            "supporting_story_ids": record.supporting_story_ids,
            "supporting_thesis_ids": record.supporting_thesis_ids,
            "supporting_action_ids": record.supporting_action_ids,
            "supporting_outcome_ids": record.supporting_outcome_ids,
            "evidence_json": ClickHouseClient._json_string(record.evidence),
            "recommended_route_json": ClickHouseClient._json_string(record.recommended_route),
            "recommended_action": record.recommended_action or "",
            "created_by_agent": record.created_by_agent,
            "model": record.model,
            "adapter": record.adapter,
            "schema_version": record.schema_version,
            "outcome_status": record.outcome_status.value,
            "created_at": ClickHouseClient._format_datetime(record.created_at),
        }

    @staticmethod
    def _serialize_route_prediction(record: RoutePrediction) -> dict[str, Any]:
        return {
            "id": record.id or "",
            "navigation_signal_id": record.navigation_signal_id,
            "route_type": record.route_type,
            "origin": record.origin,
            "destination": record.destination,
            "expected_flow_direction": record.expected_flow_direction.value,
            "expected_flow_magnitude": record.expected_flow_magnitude.value,
            "time_horizon_hours": record.time_horizon_hours,
            "confidence": record.confidence,
            "hazards": record.hazards,
            "supporting_story_ids": record.supporting_story_ids,
            "created_by_agent": record.created_by_agent or "",
            "model": record.model or "",
            "adapter": record.adapter or "",
            "schema_version": record.schema_version or "",
            "created_at": ClickHouseClient._format_datetime(record.created_at),
        }

    @staticmethod
    def _serialize_traffic_state(record: TrafficState) -> dict[str, Any]:
        return {
            "id": record.id or "",
            "scope": record.scope,
            "market_state": record.market_state.value,
            "dominant_flows_json": ClickHouseClient._json_string(record.dominant_flows),
            "congestion_zones": record.congestion_zones,
            "hazards": record.hazards,
            "top_destinations_json": ClickHouseClient._json_string(record.top_destinations),
            "created_by_agent": record.created_by_agent,
            "model": "",
            "adapter": "",
            "schema_version": "",
            "created_at": ClickHouseClient._format_datetime(record.created_at),
        }

    @staticmethod
    def _serialize_prediction_outcome(record: PredictionOutcome) -> dict[str, Any]:
        return {
            "id": record.id or "",
            "navigation_signal_id": record.navigation_signal_id,
            "route_prediction_id": record.route_prediction_id or "",
            "evaluation_window_hours": record.evaluation_window_hours,
            "prediction_accuracy": record.prediction_accuracy,
            "realized_direction": record.realized_direction.value,
            "realized_magnitude": record.realized_magnitude.value,
            "map_prediction_correct": int(record.map_prediction_correct),
            "notes": record.notes,
            "created_by_agent": record.created_by_agent,
            "model": "",
            "adapter": "",
            "schema_version": "",
            "created_at": ClickHouseClient._format_datetime(record.created_at),
            # Phase 12 dual-witness fields
            "heuristic_accuracy": record.heuristic_accuracy,
            "quantitative_accuracy": record.quantitative_accuracy,
            "scorer_agreement": record.scorer_agreement,
            "scoring_method": record.scoring_method.value,
            "consumer_exposure": record.consumer_exposure,
            "exogenous_accuracy": record.exogenous_accuracy,
            "induced_accuracy": record.induced_accuracy,
        }

    @staticmethod
    def _serialize_maps_news_brief(record: MapsNewsBrief) -> dict[str, Any]:
        return {
            "id": record.id,
            "scope": record.scope,
            "headline": record.headline,
            "summary": record.summary,
            "stance": record.stance,
            "supporting_signal_ids": record.supporting_signal_ids,
            "supporting_story_ids": record.supporting_story_ids,
            "supporting_thesis_ids": record.supporting_thesis_ids,
            "tags": record.tags,
            "created_by_agent": record.created_by_agent,
            "model": record.model,
            "adapter": record.adapter,
            "schema_version": record.schema_version,
            "created_at": ClickHouseClient._format_datetime(record.created_at),
        }

    @staticmethod
    def _serialize_watch_prediction(record: WatchPrediction) -> dict[str, Any]:
        return {
            "id": record.id or "",
            "source_signal_id": record.source_signal_id,
            "source_prediction_id": record.source_prediction_id or "",
            "signal_type": record.signal_type.value,
            "asset_scope": record.asset_scope,
            "chain_scope": record.chain_scope,
            "claim": record.claim,
            "probability": record.probability,
            "realized_direction_expected": record.realized_direction_expected.value,
            "magnitude_expected": record.magnitude_expected.value,
            "evaluation_window_hours": record.evaluation_window_hours,
            "status": record.status.value,
            "created_by_agent": record.created_by_agent,
            "model": record.model,
            "adapter": record.adapter,
            "schema_version": record.schema_version,
            "idempotency_key": record.idempotency_key,
            "created_at": ClickHouseClient._format_datetime(record.created_at),
        }

    @staticmethod
    def _serialize_watch_draft(record: WatchDraft) -> dict[str, Any]:
        return {
            "id": record.id or "",
            "watch_prediction_id": record.watch_prediction_id,
            "headline": record.headline,
            "analysis": record.analysis,
            "significance": record.significance,
            "x_post": record.x_post,
            "linkedin_draft": record.linkedin_draft,
            "track_record_snapshot": ClickHouseClient._json_string(record.track_record_snapshot),
            "routing": ClickHouseClient._json_string(record.routing),
            "status": record.status.value,
            "created_by_agent": record.created_by_agent,
            "model": record.model,
            "adapter": record.adapter,
            "schema_version": record.schema_version,
            "created_at": ClickHouseClient._format_datetime(record.created_at),
        }

    @staticmethod
    def _serialize_consumer_attestation(record: ConsumerAttestation) -> dict[str, Any]:
        return {
            "id": record.id or "",
            "watch_prediction_id": record.watch_prediction_id,
            "consumer_id": record.consumer_id,
            "acted": int(record.acted),
            "observed_direction": record.observed_direction.value
            if record.observed_direction
            else "",
            "observed_magnitude": record.observed_magnitude.value
            if record.observed_magnitude
            else "",
            "notes": record.notes,
            "created_at": ClickHouseClient._format_datetime(record.created_at),
        }

    @staticmethod
    def _serialize_cross_chain_activity_state(record: CrossChainActivityState) -> dict[str, Any]:
        return {
            "id": record.id,
            "scope": record.scope,
            "market_bias": record.market_bias,
            "top_routes_json": ClickHouseClient._json_string(record.top_routes),
            "active_hazards_json": ClickHouseClient._json_string(record.active_hazards),
            "active_congestion_json": ClickHouseClient._json_string(record.active_congestion),
            "top_destinations_json": ClickHouseClient._json_string(record.top_destinations),
            "ethereum_outbound_routes_json": ClickHouseClient._json_string(
                record.ethereum_outbound_routes
            ),
            "ethereum_inbound_routes_json": ClickHouseClient._json_string(
                record.ethereum_inbound_routes
            ),
            "supporting_signal_ids": record.supporting_signal_ids,
            "created_by_agent": record.created_by_agent,
            "schema_version": record.schema_version,
            "created_at": ClickHouseClient._format_datetime(record.created_at),
        }

    @staticmethod
    def _serialize_signal_utility_score(record: SignalUtilityScore) -> dict[str, Any]:
        return {
            "id": record.id or "",
            "navigation_signal_id": record.navigation_signal_id,
            "sample_size": record.sample_size,
            "prediction_accuracy": record.prediction_accuracy,
            "economic_utility": record.economic_utility,
            "risk_reduction_utility": record.risk_reduction_utility,
            "confidence_calibration_error": record.confidence_calibration_error,
            "execution_adjusted_utility": record.execution_adjusted_utility,
            "final_signal_utility_score": record.final_signal_utility_score,
            "linked_action_ids": record.linked_action_ids,
            "linked_outcome_ids": record.linked_outcome_ids,
            "created_at": ClickHouseClient._format_datetime(record.created_at),
        }

    @staticmethod
    def _serialize_flow_graph_snapshot(record: FlowGraphSnapshot) -> dict[str, Any]:
        return {
            "id": record.id or "",
            "signal_count": record.signal_count,
            "node_count": record.node_count,
            "edge_count": record.edge_count,
            "created_at": ClickHouseClient._format_datetime(record.created_at),
        }

    @staticmethod
    def _serialize_flow_edge(record: FlowEdge) -> dict[str, Any]:
        return {
            "id": record.id or "",
            "snapshot_id": record.snapshot_id,
            "origin": record.origin,
            "destination": record.destination,
            "strength": record.strength.value,
            "confidence": record.confidence,
            "hazard_level": record.hazard_level.value,
            "source_signal_ids": record.source_signal_ids,
            "edge_status": record.edge_status.value,
            "created_at": ClickHouseClient._format_datetime(record.created_at),
        }

    @staticmethod
    def _json_string(value: Any) -> str:
        if value is None:
            return ""
        normalized = ClickHouseClient._normalize_json_value(value)
        return json.dumps(normalized, separators=(",", ":"), sort_keys=True)

    @staticmethod
    def _normalize_json_value(value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        if hasattr(value, "model_dump"):
            return ClickHouseClient._normalize_json_value(value.model_dump(mode="json"))
        if hasattr(value, "dict"):
            return ClickHouseClient._normalize_json_value(value.dict())
        if isinstance(value, dict):
            return {
                key: ClickHouseClient._normalize_json_value(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [ClickHouseClient._normalize_json_value(item) for item in value]
        return value

    @staticmethod
    def _format_datetime(value: datetime) -> str:
        if value.tzinfo is None:
            normalized = value
        else:
            normalized = value.astimezone(UTC).replace(tzinfo=None)
        return normalized.strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _sql_string(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"
