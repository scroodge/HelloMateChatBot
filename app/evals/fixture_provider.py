"""Offline provider used by CI to evaluate checked-in synthetic fixtures."""

from __future__ import annotations

from time import monotonic

from app.evals.core import EvaluationError, ReplyGenerator
from app.models.generation import GenerationRequest, GenerationResult


class FixtureProvider(ReplyGenerator):
    """Return the checked-in synthetic response selected by the case user input."""

    provider_name = "fixture"
    model = "synthetic-regression-v1"

    def __init__(self, replies: dict[str, str]) -> None:
        self.replies = replies

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        started = monotonic()
        user_content = request.messages[-1]["content"]
        try:
            text = self.replies[user_content]
        except KeyError as exc:
            raise EvaluationError(
                "Fixture response missing for generated evaluation message"
            ) from exc
        return GenerationResult(
            text=text,
            provider=self.provider_name,
            model=self.model,
            response_id=None,
            input_tokens=None,
            output_tokens=None,
            cached_tokens=None,
            finish_reason="fixture",
            latency_ms=round((monotonic() - started) * 1000),
        )
