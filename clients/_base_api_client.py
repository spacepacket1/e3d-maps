from __future__ import annotations

import json
import time
from math import ceil
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class E3DAPIClientError(RuntimeError):
    """Raised when an E3D API read fails after retries."""


class BaseE3DReadClient:
    def __init__(
        self,
        *,
        base_url: str = "https://e3d.ai",
        api_prefix: str = "/api",
        api_key: str | None = None,
        timeout: float = 10.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.25,
        request_executor=None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_prefix = self._normalize_path(api_prefix)
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self._request_executor = request_executor or self._default_request_executor

    def _get_json(
        self,
        *,
        path: str,
        query: Mapping[str, Any] | None = None,
        missing_ok: bool = False,
    ) -> Any:
        url = self._build_url(path=path, query=query)
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = Request(url=url, headers=headers, method="GET")
        attempts = max(1, self.max_retries + 1)
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                raw = self._request_executor(request, self.timeout)
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
            except HTTPError as exc:
                if missing_ok and exc.code == 404:
                    return None
                if exc.code < 500 or attempt == attempts - 1:
                    detail = exc.read().decode("utf-8", errors="replace")
                    raise E3DAPIClientError(
                        f"E3D API request failed with status {exc.code}: {detail}"
                    ) from exc
                last_error = exc
            except URLError as exc:
                if attempt == attempts - 1:
                    raise E3DAPIClientError(f"E3D API request failed: {exc.reason}") from exc
                last_error = exc

            if self.retry_backoff_seconds > 0:
                time.sleep(self.retry_backoff_seconds * (attempt + 1))

        raise E3DAPIClientError("E3D API request failed after retries") from last_error

    def _build_url(self, *, path: str, query: Mapping[str, Any] | None) -> str:
        full_path = f"{self.api_prefix}{self._normalize_path(path)}"
        if not query:
            return f"{self.base_url}{full_path}"

        filtered_query = {
            key: value
            for key, value in query.items()
            if value is not None
        }
        encoded_query = urlencode(filtered_query, doseq=True)
        if not encoded_query:
            return f"{self.base_url}{full_path}"
        return f"{self.base_url}{full_path}?{encoded_query}"

    @staticmethod
    def _normalize_path(path: str) -> str:
        if not path:
            return ""
        return path if path.startswith("/") else f"/{path}"

    @staticmethod
    def _coerce_items(payload: Any, *, max_items: int) -> list[dict[str, Any]]:
        items: Any = payload
        if payload is None:
            return []
        if isinstance(payload, Mapping):
            for key in ("items", "results", "data", "stories", "theses", "actions", "outcomes", "verdicts"):
                if key in payload:
                    items = payload[key]
                    break

        if not isinstance(items, list):
            return []

        bounded_items = items[: max(0, max_items)]
        return [item for item in bounded_items if isinstance(item, dict)]

    @staticmethod
    def _estimate_tokens(value: Any) -> int:
        serialized = json.dumps(value, separators=(",", ":"), sort_keys=True)
        return ceil(len(serialized) / 4)

    @staticmethod
    def _default_request_executor(request: Request, timeout: float) -> bytes:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
