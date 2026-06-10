from __future__ import annotations

import json
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from settings import MapsRuntimeSettings


class QwenClientError(RuntimeError):
    """Raised when a Qwen request fails or returns an invalid payload."""


class QwenClient:
    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:5050",
        completions_path: str = "/v1/chat/completions",
        default_model: str = "mlx-community/Qwen2.5-14B-Instruct-4bit",
        api_key: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 1,
        retry_backoff_seconds: float = 0.5,
        adapter_header_name: str = "X-Adapter-Path",
        request_executor=None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.completions_path = self._normalize_path(completions_path)
        self.default_model = default_model
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.adapter_header_name = adapter_header_name
        self._request_executor = request_executor or self._default_request_executor

    @classmethod
    def from_settings(
        cls,
        settings: MapsRuntimeSettings,
        *,
        request_executor=None,
    ) -> "QwenClient":
        return cls(
            base_url=settings.qwen_base_url,
            completions_path=settings.qwen_completions_path,
            default_model=settings.qwen_model,
            api_key=settings.qwen_api_key,
            request_executor=request_executor,
        )

    def generate(
        self,
        *,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
        adapter_name: str | None = None,
        adapter_path: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: Mapping[str, Any] | None = None,
        extra_body: Mapping[str, Any] | None = None,
    ) -> str:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if response_format:
            payload["response_format"] = dict(response_format)
        if extra_body:
            payload.update(dict(extra_body))

        extra_headers: dict[str, str] = {}
        if adapter_path and self.adapter_header_name:
            extra_headers[self.adapter_header_name] = adapter_path

        response_payload = self._post_json(
            path=self.completions_path,
            payload=payload,
            extra_headers=extra_headers,
        )
        return self._extract_message_content(response_payload)

    def _post_json(
        self,
        *,
        path: str,
        payload: Mapping[str, Any],
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{self._normalize_path(path)}"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if extra_headers:
            headers.update(extra_headers)

        request = Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        attempts = max(1, self.max_retries + 1)
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                raw = self._request_executor(request, self.timeout)
                if not raw:
                    raise QwenClientError("Qwen response was empty")
                parsed = json.loads(raw.decode("utf-8"))
                if not isinstance(parsed, dict):
                    raise QwenClientError("Qwen response must be a JSON object")
                return parsed
            except HTTPError as exc:
                if exc.code < 500 or attempt == attempts - 1:
                    detail = exc.read().decode("utf-8", errors="replace")
                    raise QwenClientError(
                        f"Qwen request failed with status {exc.code}: {detail}"
                    ) from exc
                last_error = exc
            except URLError as exc:
                if attempt == attempts - 1:
                    raise QwenClientError(f"Qwen request failed: {exc.reason}") from exc
                last_error = exc
            except OSError as exc:
                if attempt == attempts - 1:
                    raise QwenClientError(f"Qwen request failed: {exc}") from exc
                last_error = exc

            if self.retry_backoff_seconds > 0:
                time.sleep(self.retry_backoff_seconds * (attempt + 1))

        raise QwenClientError("Qwen request failed after retries") from last_error

    @staticmethod
    def _extract_message_content(payload: Mapping[str, Any]) -> str:
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first_choice = choices[0]
            if isinstance(first_choice, Mapping):
                message = first_choice.get("message")
                if isinstance(message, Mapping):
                    content = message.get("content")
                    if isinstance(content, str) and content.strip():
                        return content

        for key in ("output_text", "response", "content"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value

        raise QwenClientError("Qwen response did not contain message content")

    @staticmethod
    def _normalize_path(path: str) -> str:
        if not path:
            return ""
        return path if path.startswith("/") else f"/{path}"

    @staticmethod
    def _default_request_executor(request: Request, timeout: float) -> bytes:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
