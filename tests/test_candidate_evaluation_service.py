"""Failure handling for owner-triggered candidate evaluations."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.services.candidate_evaluation_service import CandidateEvaluationService


class FakeSettings:
    def __init__(self, value: str) -> None:
        self.value = value

    def get_bot_setting(self, key: str, default: str) -> str:
        return self.value

    def set_bot_setting(self, key: str, value: str) -> None:
        self.value = value


@pytest.mark.asyncio
async def test_evaluation_provider_failure_is_saved_not_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = FakeSettings(
        json.dumps(
            [
                {
                    "id": "candidate-1",
                    "name": "Broken provider",
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "base_url": "https://api.openai.com",
                    "credential_id": "openai",
                    "status": "new",
                }
            ]
        )
    )
    service = CandidateEvaluationService(
        settings,
        MagicMock(llm_provider="ollama", llm_model="test", llm_base_url="http://ollama"),
    )

    async def raise_provider_error(*args: object, **kwargs: object) -> object:
        raise RuntimeError("provider rejected request")

    monkeypatch.setattr(service, "_provider", lambda candidate: object())
    monkeypatch.setattr("app.services.candidate_evaluation_service.run_cases", raise_provider_error)
    result = await service.evaluate("candidate-1")

    assert result is not None
    assert result["status"] == "failed"
    assert result["summary"]["error"] == "provider rejected request"
    assert json.loads(settings.value)[0]["status"] == "failed"


def test_direct_openai_gpt5_candidate_gets_reasoning_budget() -> None:
    service = CandidateEvaluationService(
        FakeSettings("[]"),
        MagicMock(llm_provider="ollama", llm_model="test", llm_base_url="http://ollama"),
    )
    service._credential = lambda candidate: "secret"  # type: ignore[method-assign]

    provider = service._provider(
        {
            "provider": "openai",
            "model": "gpt-5-mini",
            "base_url": "https://api.openai.com",
            "credential_id": "openai",
        }
    )

    assert provider.max_tokens == 1024
    assert provider.reasoning_effort == "minimal"
