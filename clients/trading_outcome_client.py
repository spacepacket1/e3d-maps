from __future__ import annotations

from typing import Any

from clients._base_api_client import BaseE3DReadClient


class TradingOutcomeClient(BaseE3DReadClient):
    DEFAULT_ACTIONS_MAX_ITEMS = 20
    DEFAULT_OUTCOMES_MAX_ITEMS = 20
    DEFAULT_VERDICTS_MAX_ITEMS = 20

    def __init__(
        self,
        *,
        actions_path: str = "/trading/actions",
        outcomes_path: str = "/trading/outcomes",
        verdicts_path: str = "/trading/verdicts",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.actions_path = actions_path
        self.outcomes_path = outcomes_path
        self.verdicts_path = verdicts_path

    def get_recent_actions(self, *, max_items: int = DEFAULT_ACTIONS_MAX_ITEMS) -> list[dict[str, Any]]:
        payload = self._get_json(
            path=self.actions_path,
            query={"limit": max_items},
            missing_ok=True,
        )
        return self._coerce_items(payload, max_items=max_items)

    def get_recent_outcomes(
        self,
        *,
        max_items: int = DEFAULT_OUTCOMES_MAX_ITEMS,
    ) -> list[dict[str, Any]]:
        payload = self._get_json(
            path=self.outcomes_path,
            query={"limit": max_items},
            missing_ok=True,
        )
        return self._coerce_items(payload, max_items=max_items)

    def get_recent_verdicts(
        self,
        *,
        max_items: int = DEFAULT_VERDICTS_MAX_ITEMS,
    ) -> list[dict[str, Any]]:
        payload = self._get_json(
            path=self.verdicts_path,
            query={"limit": max_items},
            missing_ok=True,
        )
        return self._coerce_items(payload, max_items=max_items)

    def get_actions_linked_to_navigation_signal(
        self,
        navigation_signal_id: str,
        *,
        max_items: int = DEFAULT_ACTIONS_MAX_ITEMS,
    ) -> list[dict[str, Any]]:
        payload = self._get_json(
            path=self.actions_path,
            query={
                "navigation_signal_id": navigation_signal_id,
                "limit": max_items,
            },
            missing_ok=True,
        )
        return self._coerce_items(payload, max_items=max_items)

    def get_actions_linked_to_route_prediction(
        self,
        route_prediction_id: str,
        *,
        max_items: int = DEFAULT_ACTIONS_MAX_ITEMS,
    ) -> list[dict[str, Any]]:
        payload = self._get_json(
            path=self.actions_path,
            query={
                "route_prediction_id": route_prediction_id,
                "limit": max_items,
            },
            missing_ok=True,
        )
        return self._coerce_items(payload, max_items=max_items)
