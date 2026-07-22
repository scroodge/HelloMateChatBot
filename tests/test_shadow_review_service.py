"""Owner-triggered blind review workflow."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.generation import GenerationResult
from app.services.shadow_review_service import ShadowReviewService


class FakeRepository:
    def __init__(self) -> None:
        self.review = SimpleNamespace(
            id=1,
            user_id=7,
            candidate_id="candidate-gpt5",
            message_text="Привет! Как дела?",
            reply_a=None,
            reply_b=None,
            mapping=None,
            status="queued",
            winner=None,
            error=None,
            created_at=datetime.now().astimezone(),
        )

    def create(self, user_id: int, candidate_id: str, message_text: str) -> object:
        self.review.user_id, self.review.candidate_id, self.review.message_text = (
            user_id,
            candidate_id,
            message_text,
        )
        return self.review

    def get(self, review_id: int) -> object:
        return self.review

    def complete(self, review_id: int, reply_a: str, reply_b: str, mapping: str) -> None:
        self.review.reply_a, self.review.reply_b, self.review.mapping = reply_a, reply_b, mapping
        self.review.status = "ready"

    def fail(self, review_id: int, error: str) -> None:
        self.review.status, self.review.error = "failed", error

    def resolve(self, review_id: int, winner: str) -> object:
        self.review.status, self.review.winner = "resolved", winner
        return self.review

    def recent(self, *, limit: int = 20) -> list[object]:
        return [self.review]


@pytest.mark.asyncio
async def test_shadow_review_uses_same_compiled_messages_and_blinds_mapping(monkeypatch) -> None:
    repository = FakeRepository()
    reply_service = MagicMock()
    reply_service.preview_reply = AsyncMock(
        return_value={
            "reply": "Ответ baseline",
            "assembled_messages": [{"role": "user", "content": "x"}],
        }
    )
    candidate_service = MagicMock()
    candidate_service.generate_shadow = AsyncMock(
        return_value=GenerationResult(
            text="Ответ кандидата", provider="openai", model="gpt-5-mini", response_id=None,
            input_tokens=1, output_tokens=1, cached_tokens=None, finish_reason="stop", latency_ms=1,
        )
    )
    jobs = MagicMock()
    service = ShadowReviewService(repository, reply_service, candidate_service, jobs)
    monkeypatch.setattr("app.services.shadow_review_service.random.choice", lambda _: True)

    queued = service.queue(7, "candidate-gpt5", "Привет! Как дела?")
    await service.run(queued.id)

    jobs.enqueue.assert_called_once()
    candidate_service.generate_shadow.assert_awaited_once_with(
        "candidate-gpt5", [{"role": "user", "content": "x"}]
    )
    assert repository.review.reply_a == "Ответ baseline"
    assert repository.review.reply_b == "Ответ кандидата"
    assert repository.review.mapping == "a=baseline"


def test_resolved_blind_review_reveals_whether_baseline_won() -> None:
    service = ShadowReviewService(FakeRepository(), MagicMock(), MagicMock(), MagicMock())
    service._repository.review.mapping = "b=baseline"  # type: ignore[attr-defined]

    result = service.resolve(1, "b")

    assert result == {"id": 1, "winner": "b", "baseline_selected": True}
