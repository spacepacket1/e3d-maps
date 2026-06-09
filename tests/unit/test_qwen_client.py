from __future__ import annotations

import json
from urllib.error import HTTPError

import pytest

from clients.qwen_client import QwenClient, QwenClientError


def test_generate_posts_chat_completion_request_and_returns_message_content():
    captured = {}

    def request_executor(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return json.dumps(
            {"choices": [{"message": {"content": "{\"signal_type\":\"capital_migration\"}"}}]}
        ).encode("utf-8")

    client = QwenClient(
        base_url="http://qwen.local:8000",
        completions_path="/v1/chat/completions",
        default_model="qwen2.5",
        api_key="secret",
        timeout=12.5,
        request_executor=request_executor,
    )

    response = client.generate(
        prompt="Where is capital moving?",
        system_prompt="Return JSON only.",
        adapter_name="maps-v0.1",
        adapter_path="/models/maps-v0.1",
        max_tokens=400,
    )

    assert response == "{\"signal_type\":\"capital_migration\"}"
    assert captured["url"] == "http://qwen.local:8000/v1/chat/completions"
    assert captured["timeout"] == 12.5
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["headers"]["X-adapter-path"] == "/models/maps-v0.1"
    assert captured["body"] == {
        "model": "qwen2.5",
        "messages": [
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": "Where is capital moving?"},
        ],
        "temperature": 0.0,
        "max_tokens": 400,
    }


def test_generate_can_read_flat_output_text_response():
    def request_executor(request, timeout):
        return json.dumps({"output_text": "null"}).encode("utf-8")

    client = QwenClient(request_executor=request_executor)

    assert client.generate(prompt="Return null.") == "null"


def test_generate_retries_transient_http_failures():
    attempts = {"count": 0}

    def request_executor(request, timeout):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise HTTPError(request.full_url, 503, "Unavailable", hdrs=None, fp=None)
        return json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode("utf-8")

    client = QwenClient(
        request_executor=request_executor,
        max_retries=2,
        retry_backoff_seconds=0,
    )

    assert client.generate(prompt="Return {}.") == "{}"
    assert attempts["count"] == 3


def test_generate_raises_when_response_has_no_content():
    def request_executor(request, timeout):
        return json.dumps({"choices": [{"message": {}}]}).encode("utf-8")

    client = QwenClient(request_executor=request_executor)

    with pytest.raises(QwenClientError, match="did not contain message content"):
        client.generate(prompt="Return JSON.")
