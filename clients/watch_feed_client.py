from __future__ import annotations

import os
from typing import Any

from clients._base_api_client import BaseE3DReadClient

DEFAULT_MAPS_PUBLIC_API_BASE = "https://e3d.ai"


class WatchFeedClient(BaseE3DReadClient):
    """Public-contract consumer of the E3D Maps ``/api/maps/...`` surface.

    This is the reference implementation downstream agents copy: it reads Maps
    over HTTP only and MUST NOT import producer modules. It demonstrates
    ecosystem-grade hygiene — ``Authorization: Bearer`` auth, retry/backoff
    (inherited from ``BaseE3DReadClient``), and cursor/``since`` incremental
    fetch so notable events are never reprocessed or skipped.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        notable_path: str = "/maps/notable",
        signal_path: str = "/maps/signals",
        predictions_path: str = "/maps/predictions",
        calibration_path: str = "/maps/calibration",
        **kwargs,
    ) -> None:
        resolved_base = base_url or os.environ.get(
            "MAPS_PUBLIC_API_BASE", DEFAULT_MAPS_PUBLIC_API_BASE
        )
        super().__init__(base_url=resolved_base, **kwargs)
        self.notable_path = notable_path
        self.signal_path = signal_path
        self.predictions_path = predictions_path
        self.calibration_path = calibration_path
        self._notable_cursor: str | None = None

    def _auth_headers(self) -> dict[str, str]:
        if self.api_key:
            return {"Authorization": f"Bearer {self.api_key}"}
        return {}

    @property
    def notable_cursor(self) -> str | None:
        return self._notable_cursor

    def get_notable(
        self,
        *,
        min_score: int = 0,
        since: str | None = None,
        limit: int = 50,
        advance_cursor: bool = True,
    ) -> list[dict[str, Any]]:
        """Fetch notable signals at/above ``min_score``.

        Incremental fetch: when ``since`` is omitted the client uses its stored
        cursor (the newest ``created_at`` seen so far), so repeated calls never
        reprocess or skip events. The cursor advances to the newest returned
        ``created_at`` unless ``advance_cursor`` is False.
        """
        effective_since = since if since is not None else self._notable_cursor
        payload = self._get_json(
            path=self.notable_path,
            query={"min_score": min_score, "since": effective_since, "limit": limit},
            missing_ok=True,
        )
        items = self._extract_list(payload, key="notable", max_items=limit)
        if advance_cursor and items:
            newest = max((item.get("created_at") or "") for item in items)
            if newest:
                self._notable_cursor = newest
        return items

    def get_signal(self, signal_id: str) -> dict[str, Any] | None:
        payload = self._get_json(
            path=f"{self.signal_path}/{signal_id}",
            missing_ok=True,
        )
        if isinstance(payload, dict):
            signal = payload.get("signal")
            if isinstance(signal, dict):
                return signal
        return None

    def get_predictions(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        payload = self._get_json(
            path=self.predictions_path,
            query={"limit": limit, "offset": offset},
            missing_ok=True,
        )
        return self._extract_list(payload, key="predictions", max_items=limit)

    def get_calibration(self, *, source: str = "watch_agent") -> dict[str, Any]:
        payload = self._get_json(
            path=self.calibration_path,
            query={"source": source},
            missing_ok=True,
        )
        if isinstance(payload, dict):
            calibration = payload.get("calibration")
            if isinstance(calibration, dict):
                return calibration
        return {}

    @staticmethod
    def _extract_list(payload: Any, *, key: str, max_items: int) -> list[dict[str, Any]]:
        items: Any = []
        if isinstance(payload, dict):
            items = payload.get(key, payload.get("items", []))
        elif isinstance(payload, list):
            items = payload
        if not isinstance(items, list):
            return []
        bounded = items[: max(0, max_items)]
        return [item for item in bounded if isinstance(item, dict)]
