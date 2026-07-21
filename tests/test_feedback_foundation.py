"""Phase 18 traces and Suggest Inbox feedback lifecycle."""

from __future__ import annotations

from sqlalchemy import select

from app.database.db import Database
from app.database.schema import feedback_events, generation_runs, suggestion_outcomes
from app.models.generation import GenerationRequest, GenerationResult
from app.services.llm import LLMService
from app.services.suggestions_service import SuggestionsService


class _Provider:
    provider_name = "test-provider"
    model = "test-model"

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        return GenerationResult(
            text="private reply",
            provider=self.provider_name,
            model=self.model,
            response_id="response-1",
            input_tokens=11,
            output_tokens=7,
            cached_tokens=2,
            finish_reason="stop",
            latency_ms=42,
        )


async def test_generation_trace_records_metadata_but_not_prompt_or_reply(tmp_path) -> None:
    with Database(f"sqlite:///{tmp_path / 'feedback.db'}") as db:
        service = LLMService(_Provider(), db.feedback)
        result = await service.generate(
            GenerationRequest(
                messages=[{"role": "user", "content": "sensitive prompt"}],
                purpose="draft",
                contact_user_id=42,
                prompt_version="v1",
                context_policy_version="v1",
            )
        )
        with db.engine.connect() as conn:
            row = conn.execute(select(generation_runs)).one()

    assert result.trace_id == row.trace_id
    assert row.user_id == 42
    assert row.provider == "test-provider"
    assert row.input_tokens == 11
    assert "sensitive prompt" not in str(dict(row._mapping))
    assert "private reply" not in str(dict(row._mapping))


def test_suggestion_feedback_is_append_only_and_captures_edit_outcome(tmp_path) -> None:
    with Database(f"sqlite:///{tmp_path / 'feedback.db'}") as db:
        service = SuggestionsService(db.suggestions, db.feedback)
        suggestion = service.record(42, "привет", "привет, рад тебе")
        assert suggestion is not None
        service.viewed(suggestion.id)
        service.copied(suggestion.id)
        service.accept(suggestion.id, "привет, очень рад тебе")
        with db.engine.connect() as conn:
            events = [row.event_type for row in conn.execute(select(feedback_events))]
            outcome = conn.execute(select(suggestion_outcomes)).one()

        analytics = db.feedback.analytics(user_id=42, since=None)

    assert events == ["suggestion_created", "viewed", "copied", "accepted_edited"]
    assert outcome.character_edit_distance > 0
    assert outcome.token_edit_distance > 0
    assert analytics["created"] == 1
    assert analytics["accepted_edited"] == 1
