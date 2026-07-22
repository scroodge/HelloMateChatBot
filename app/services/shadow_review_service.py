"""Owner-triggered blind review between the active model and one candidate."""

from __future__ import annotations

import random
from typing import Protocol

from app.services.candidate_evaluation_service import CandidateEvaluationService
from app.services.reply_service import ReplyService


class ShadowReviewsRepository(Protocol):
    def create(self, user_id: int, candidate_id: str, message_text: str) -> object: ...

    def get(self, review_id: int) -> object | None: ...

    def complete(self, review_id: int, reply_a: str, reply_b: str, mapping: str) -> None: ...

    def fail(self, review_id: int, error: str) -> None: ...

    def resolve(self, review_id: int, winner: str) -> object | None: ...

    def recent(self, *, limit: int = 20) -> list[object]: ...


class ShadowReviewService:
    def __init__(
        self,
        repository: ShadowReviewsRepository,
        reply_service: ReplyService,
        candidate_service: CandidateEvaluationService,
        jobs: object,
    ) -> None:
        self._repository = repository
        self._reply_service = reply_service
        self._candidate_service = candidate_service
        self._jobs = jobs

    def queue(self, user_id: int, candidate_id: str, message_text: str) -> object:
        if not message_text.strip():
            raise ValueError("Message is required")
        review = self._repository.create(user_id, candidate_id, message_text.strip())
        self._jobs.enqueue(
            "shadow_review",
            {"review_id": review.id},
            idempotency_key=f"shadow-review:{review.id}",
            max_attempts=2,
        )
        return review

    async def run(self, review_id: int) -> None:
        review = self._repository.get(review_id)
        if review is None:
            return
        try:
            baseline = await self._reply_service.preview_reply(review.user_id, review.message_text)
            candidate = await self._candidate_service.generate_shadow(
                review.candidate_id, baseline["assembled_messages"]
            )
            if random.choice((True, False)):
                reply_a, reply_b, mapping = baseline["reply"], candidate.text, "a=baseline"
            else:
                reply_a, reply_b, mapping = candidate.text, baseline["reply"], "b=baseline"
            self._repository.complete(review.id, reply_a, reply_b, mapping)
        except Exception as exc:
            self._repository.fail(review.id, str(exc))

    def recent(self) -> list[dict[str, object]]:
        rows = self._repository.recent()
        return [
            {
                "id": row.id, "user_id": row.user_id, "candidate_id": row.candidate_id,
                "reply_a": row.reply_a, "reply_b": row.reply_b, "status": row.status,
                "winner": row.winner, "error": row.error, "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]

    def resolve(self, review_id: int, winner: str) -> dict[str, object] | None:
        review = self._repository.resolve(review_id, winner)
        if review is None:
            return None
        chosen = "tie" if winner == "tie" else review.mapping.split("=")[0] == winner
        return {"id": review.id, "winner": winner, "baseline_selected": chosen}
