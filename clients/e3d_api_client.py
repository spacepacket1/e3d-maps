from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping, Sequence

from clients._base_api_client import BaseE3DReadClient


class E3DAPIClient(BaseE3DReadClient):
    DEFAULT_STORIES_MAX_ITEMS = 20
    DEFAULT_THESES_MAX_ITEMS = 10
    DEFAULT_WALLET_ACTIVITY_MAX_ITEMS = 10
    DEFAULT_TOKEN_ACTIVITY_MAX_ITEMS = 10
    DEFAULT_EXCHANGE_FLOWS_MAX_ITEMS = 10
    DEFAULT_CONTEXT_TOKEN_BUDGET = 4_000

    def __init__(
        self,
        *,
        stories_path: str = "/stories",
        theses_path: str = "/theses",
        wallet_activity_path: str = "/wallets/activity",
        token_activity_path: str = "/tokens/activity",
        exchange_flows_path: str = "/flows/exchange",
        market_state_path: str = "/market/context",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.stories_path = stories_path
        self.theses_path = theses_path
        self.wallet_activity_path = wallet_activity_path
        self.token_activity_path = token_activity_path
        self.exchange_flows_path = exchange_flows_path
        self.market_state_path = market_state_path

    def get_recent_stories(self, *, max_items: int = DEFAULT_STORIES_MAX_ITEMS) -> list[dict[str, Any]]:
        payload = self._get_json(
            path=self.stories_path,
            query={"limit": max_items},
            missing_ok=True,
        )
        return self._coerce_items(payload, max_items=max_items)

    def get_stories_within_window(
        self,
        *,
        start_time: datetime,
        end_time: datetime,
        max_items: int = DEFAULT_STORIES_MAX_ITEMS,
    ) -> list[dict[str, Any]]:
        payload = self._get_json(
            path=self.stories_path,
            query=self._window_query(start_time=start_time, end_time=end_time, limit=max_items),
            missing_ok=True,
        )
        return self._coerce_items(payload, max_items=max_items)

    def get_recent_theses(self, *, max_items: int = DEFAULT_THESES_MAX_ITEMS) -> list[dict[str, Any]]:
        payload = self._get_json(
            path=self.theses_path,
            query={"limit": max_items},
            missing_ok=True,
        )
        return self._coerce_items(payload, max_items=max_items)

    def get_wallet_activity(
        self,
        *,
        max_items: int = DEFAULT_WALLET_ACTIVITY_MAX_ITEMS,
    ) -> list[dict[str, Any]]:
        payload = self._get_json(
            path=self.wallet_activity_path,
            query={"limit": max_items},
            missing_ok=True,
        )
        return self._coerce_items(payload, max_items=max_items)

    def get_token_activity(
        self,
        *,
        max_items: int = DEFAULT_TOKEN_ACTIVITY_MAX_ITEMS,
    ) -> list[dict[str, Any]]:
        payload = self._get_json(
            path=self.token_activity_path,
            query={"limit": max_items},
            missing_ok=True,
        )
        return self._coerce_items(payload, max_items=max_items)

    def get_exchange_flows(
        self,
        *,
        max_items: int = DEFAULT_EXCHANGE_FLOWS_MAX_ITEMS,
    ) -> list[dict[str, Any]]:
        payload = self._get_json(
            path=self.exchange_flows_path,
            query={"limit": max_items},
            missing_ok=True,
        )
        return self._coerce_items(payload, max_items=max_items)

    def get_exchange_flows_within_window(
        self,
        *,
        start_time: datetime,
        end_time: datetime,
        max_items: int = DEFAULT_EXCHANGE_FLOWS_MAX_ITEMS,
    ) -> list[dict[str, Any]]:
        payload = self._get_json(
            path=self.exchange_flows_path,
            query=self._window_query(start_time=start_time, end_time=end_time, limit=max_items),
            missing_ok=True,
        )
        return self._coerce_items(payload, max_items=max_items)

    def get_stablecoin_activity_within_window(
        self,
        *,
        start_time: datetime,
        end_time: datetime,
        max_items: int = DEFAULT_TOKEN_ACTIVITY_MAX_ITEMS,
    ) -> list[dict[str, Any]]:
        payload = self._get_json(
            path=self.token_activity_path,
            query=self._window_query(start_time=start_time, end_time=end_time, limit=max_items),
            missing_ok=True,
        )
        return self._coerce_items(payload, max_items=max_items)

    def get_market_context(
        self,
        *,
        stories_max_items: int = DEFAULT_STORIES_MAX_ITEMS,
        theses_max_items: int = DEFAULT_THESES_MAX_ITEMS,
        wallet_activity_max_items: int = DEFAULT_WALLET_ACTIVITY_MAX_ITEMS,
        token_activity_max_items: int = DEFAULT_TOKEN_ACTIVITY_MAX_ITEMS,
        exchange_flows_max_items: int = DEFAULT_EXCHANGE_FLOWS_MAX_ITEMS,
        prior_signals: Sequence[Mapping[str, Any]] | None = None,
        token_budget: int = DEFAULT_CONTEXT_TOKEN_BUDGET,
    ) -> dict[str, Any]:
        market_state = self._get_json(path=self.market_state_path, missing_ok=True) or {}
        context = {
            "recent_stories": self.get_recent_stories(max_items=stories_max_items),
            "recent_theses": self.get_recent_theses(max_items=theses_max_items),
            "wallet_activity": self.get_wallet_activity(max_items=wallet_activity_max_items),
            "token_activity": self.get_token_activity(max_items=token_activity_max_items),
            "exchange_flows": self.get_exchange_flows(max_items=exchange_flows_max_items),
            "prior_signals": [dict(item) for item in prior_signals or [] if isinstance(item, Mapping)],
            "market_state": market_state if isinstance(market_state, dict) else {},
        }
        return self._trim_context_to_token_budget(context=context, token_budget=token_budget)

    def _trim_context_to_token_budget(
        self,
        *,
        context: dict[str, Any],
        token_budget: int,
    ) -> dict[str, Any]:
        if token_budget <= 0:
            return context

        trimmed = dict(context)
        drop_order = [
            "prior_signals",
            "recent_theses",
            "wallet_activity",
            "exchange_flows",
            "recent_stories",
        ]

        for key in drop_order:
            if self._estimate_tokens(trimmed) <= token_budget:
                return trimmed

            items = trimmed.get(key)
            if not isinstance(items, list) or not items:
                continue

            while items and self._estimate_tokens(trimmed) > token_budget:
                if key == "recent_stories":
                    items.pop()
                else:
                    items.pop(0)

        return trimmed

    @staticmethod
    def _window_query(
        *,
        start_time: datetime,
        end_time: datetime,
        limit: int,
    ) -> dict[str, Any]:
        return {
            "limit": max(0, limit),
            "time_min": E3DAPIClient._format_datetime(start_time),
            "time_max": E3DAPIClient._format_datetime(end_time),
        }

    @staticmethod
    def _format_datetime(value: datetime) -> str:
        if value.tzinfo is None:
            normalized = value.replace(tzinfo=UTC)
        else:
            normalized = value.astimezone(UTC)
        return normalized.isoformat().replace("+00:00", "Z")
