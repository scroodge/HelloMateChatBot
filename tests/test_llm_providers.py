"""Tests for LLM providers with mocked HTTP."""

from __future__ import annotations

import httpx
import pytest

from app.services.llm.http_client import ProviderRequestError
from app.services.llm.ollama_provider import OllamaProvider
from app.services.llm.openai_provider import OpenAIProvider


@pytest.mark.asyncio
async def test_ollama_provider_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OllamaProvider("http://ollama", "llama3.2", 128)

    class MockResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"message": {"content": "Hello from Ollama"}}

    class MockClient:
        async def __aenter__(self) -> MockClient:
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict[str, object]) -> MockResponse:
            assert url.endswith("/api/chat")
            return MockResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: MockClient())
    result = await provider.complete([{"role": "user", "content": "Hi"}])
    assert result == "Hello from Ollama"


@pytest.mark.asyncio
async def test_openai_provider_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAIProvider("https://api.openai.com", "gpt-4o-mini", "secret", 128)

    class MockResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": "Hello from OpenAI"}}]}

    class MockClient:
        async def __aenter__(self) -> MockClient:
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(
            self,
            url: str,
            json: dict[str, object],
            headers: dict[str, str],
        ) -> MockResponse:
            assert url.endswith("/v1/chat/completions")
            assert headers["Authorization"] == "Bearer secret"
            assert json["max_tokens"] == 128
            assert "max_completion_tokens" not in json
            assert json["temperature"] == provider.temperature
            assert json["stop"] == provider._STOP
            return MockResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: MockClient())
    result = await provider.complete([{"role": "user", "content": "Hi"}])
    assert result == "Hello from OpenAI"


@pytest.mark.asyncio
async def test_openai_gpt5_provider_uses_max_completion_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OpenAIProvider(
        "https://api.openai.com",
        "gpt-5-mini",
        "secret",
        128,
        reasoning_effort="minimal",
    )

    class MockResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": "Hello from GPT-5"}}]}

    class MockClient:
        async def __aenter__(self) -> MockClient:
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(
            self,
            url: str,
            json: dict[str, object],
            headers: dict[str, str],
        ) -> MockResponse:
            assert url.endswith("/v1/chat/completions")
            assert headers["Authorization"] == "Bearer secret"
            assert json["max_completion_tokens"] == 128
            assert "max_tokens" not in json
            assert "temperature" not in json
            assert "stop" not in json
            assert json["reasoning_effort"] == "minimal"
            return MockResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: MockClient())
    result = await provider.complete([{"role": "user", "content": "Hi"}])
    assert result == "Hello from GPT-5"


@pytest.mark.asyncio
async def test_provider_retries_temporary_network_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OllamaProvider("http://ollama", "llama3.2", 128, max_retries=1)
    calls = 0

    class MockResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"message": {"content": "Recovered"}}

    class MockClient:
        async def post(self, url: str, json: dict[str, object]) -> MockResponse:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise httpx.ConnectError("connection refused")
            return MockResponse()

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: MockClient())
    monkeypatch.setattr("app.services.llm.http_client.asyncio.sleep", no_sleep)

    result = await provider.complete([{"role": "user", "content": "Hi"}])

    assert result == "Recovered"
    assert calls == 2
    assert provider.health()["available"] is True


@pytest.mark.asyncio
async def test_provider_does_not_retry_permanent_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OpenAIProvider(
        "https://api.openai.com", "gpt-4o-mini", "secret", 128, max_retries=2
    )
    calls = 0

    class MockClient:
        async def post(
            self, url: str, json: dict[str, object], headers: dict[str, str]
        ) -> httpx.Response:
            nonlocal calls
            calls += 1
            request = httpx.Request("POST", url)
            return httpx.Response(401, request=request)

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: MockClient())

    with pytest.raises(ProviderRequestError) as error:
        await provider.complete([{"role": "user", "content": "Hi"}])

    assert error.value.retryable is False
    assert error.value.status_code == 401
    assert calls == 1
