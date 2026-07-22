"""Failure handling for owner-triggered candidate evaluations."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from app.models.background_job import BackgroundJob
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


def test_delete_removes_only_requested_candidate() -> None:
    settings = FakeSettings(
        json.dumps(
            [
                {"id": "candidate-1", "status": "failed"},
                {"id": "candidate-2", "status": "new"},
            ]
        )
    )
    service = CandidateEvaluationService(settings, MagicMock())

    assert service.delete("candidate-1") is True
    assert json.loads(settings.value) == [{"id": "candidate-2", "status": "new"}]
    assert service.delete("candidate-missing") is False


def test_enqueue_marks_candidate_queued_and_keeps_one_active_run() -> None:
    settings = FakeSettings(
        json.dumps([{"id": "candidate-1", "status": "failed", "evaluation_version": 2}])
    )
    jobs = MagicMock()
    jobs.enqueue.return_value = BackgroundJob(
        id=42,
        job_type="candidate_evaluation",
        payload={"candidate_id": "candidate-1"},
        idempotency_key="candidate-evaluation:candidate-1:3",
        status="pending",
        attempts=0,
        max_attempts=3,
        run_after=datetime.now().astimezone(),
        created_at=datetime.now().astimezone(),
    )
    service = CandidateEvaluationService(settings, MagicMock(), jobs)

    queued = service.enqueue_evaluation("candidate-1")

    assert queued is not None
    assert queued["status"] == "queued"
    assert queued["job_id"] == 42
    assert queued["evaluation_version"] == 3
    assert service.enqueue_evaluation("candidate-1") == queued
    jobs.enqueue.assert_called_once()
