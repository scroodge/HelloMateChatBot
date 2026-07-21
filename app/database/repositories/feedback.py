"""Persistence for private generation telemetry and Suggest Inbox feedback."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Integer, cast, func, insert, select, update

from app.database.schema import (
    feedback_events,
    generation_runs,
    suggestion_outcomes,
    suggestions,
)

if TYPE_CHECKING:
    from app.database.db import Database


class FeedbackRepositoryImpl:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add_generation_run(self, values: dict[str, Any]) -> None:
        with self._db.engine.begin() as conn:
            conn.execute(insert(generation_runs).values(**values))

    def link_generation_run(self, trace_id: str, suggestion_id: int) -> None:
        with self._db.engine.begin() as conn:
            conn.execute(
                update(generation_runs)
                .where(generation_runs.c.trace_id == trace_id)
                .values(suggestion_id=suggestion_id)
            )

    def recent_generation_runs(self, *, limit: int = 30) -> list[dict[str, Any]]:
        """Return owner-safe generation metadata, newest first.

        Prompts and model replies deliberately stay out of this operational feed.
        The linked Suggest Inbox status tells the owner whether a draft still
        needs attention without duplicating its content here.
        """
        query = (
            select(
                generation_runs.c.trace_id,
                generation_runs.c.user_id,
                generation_runs.c.purpose,
                generation_runs.c.provider,
                generation_runs.c.model,
                generation_runs.c.prompt_version,
                generation_runs.c.context_policy_version,
                generation_runs.c.latency_ms,
                generation_runs.c.finish_reason,
                generation_runs.c.error_code,
                generation_runs.c.created_at,
                suggestions.c.status.label("suggestion_status"),
            )
            .select_from(
                generation_runs.outerjoin(
                    suggestions, generation_runs.c.suggestion_id == suggestions.c.id
                )
            )
            .order_by(generation_runs.c.id.desc())
            .limit(max(1, min(limit, 100)))
        )
        with self._db.engine.connect() as conn:
            rows = conn.execute(query).mappings().all()
        return [dict(row) for row in rows]

    def add_feedback_event(
        self,
        suggestion_id: int,
        event_type: str,
        *,
        reason: str | None = None,
    ) -> None:
        with self._db.engine.begin() as conn:
            conn.execute(
                insert(feedback_events).values(
                    suggestion_id=suggestion_id,
                    event_type=event_type,
                    reason=reason,
                    created_at=datetime.now().astimezone().isoformat(),
                )
            )

    def save_outcome(
        self,
        suggestion_id: int,
        final_text: str,
        character_edit_distance: int,
        token_edit_distance: int,
        semantic_similarity: float,
        decision_seconds: int,
    ) -> None:
        now = datetime.now().astimezone().isoformat()
        values = dict(
            suggestion_id=suggestion_id,
            final_text=final_text,
            character_edit_distance=character_edit_distance,
            token_edit_distance=token_edit_distance,
            semantic_similarity=semantic_similarity,
            decision_seconds=decision_seconds,
            created_at=now,
        )
        with self._db.engine.begin() as conn:
            conn.execute(insert(suggestion_outcomes).values(**values))

    def analytics(self, *, user_id: int | None, since: datetime | None) -> dict[str, Any]:
        event_query = select(feedback_events.c.event_type, func.count().label("count")).select_from(
            feedback_events.join(suggestions, feedback_events.c.suggestion_id == suggestions.c.id)
        )
        if user_id is not None:
            event_query = event_query.where(suggestions.c.user_id == user_id)
        if since is not None:
            event_query = event_query.where(feedback_events.c.created_at >= since.isoformat())
        event_query = event_query.group_by(feedback_events.c.event_type)
        with self._db.engine.connect() as conn:
            counts = {row.event_type: int(row.count) for row in conn.execute(event_query)}
            runs_query = select(
                generation_runs.c.provider,
                generation_runs.c.model,
                func.avg(generation_runs.c.latency_ms).label("latency_ms"),
                func.sum(cast(generation_runs.c.error_code.is_not(None), Integer)).label("errors"),
            ).where(generation_runs.c.purpose.in_(("draft", "reply", "preview")))
            if user_id is not None:
                runs_query = runs_query.where(generation_runs.c.user_id == user_id)
            if since is not None:
                runs_query = runs_query.where(generation_runs.c.created_at >= since.isoformat())
            run_rows = conn.execute(
                runs_query.group_by(generation_runs.c.provider, generation_runs.c.model)
            )
            provider_rows = [
                {
                    "provider": row.provider,
                    "model": row.model,
                    "latency_ms": round(row.latency_ms or 0),
                    "errors": int(row.errors or 0),
                }
                for row in run_rows
            ]
            median_query = select(suggestion_outcomes.c.decision_seconds).select_from(
                suggestion_outcomes.join(
                    suggestions, suggestion_outcomes.c.suggestion_id == suggestions.c.id
                )
            )
            if user_id is not None:
                median_query = median_query.where(suggestions.c.user_id == user_id)
            decision_values = sorted(
                int(row.decision_seconds) for row in conn.execute(median_query)
            )
        median = decision_values[len(decision_values) // 2] if decision_values else None
        return {
            "created": counts.get("suggestion_created", 0),
            "accepted_as_is": counts.get("accepted_as_is", 0),
            "accepted_edited": counts.get("accepted_edited", 0),
            "dismissed": counts.get("dismissed", 0),
            "owner_replied": counts.get("owner_replied", 0),
            "median_decision_seconds": median,
            "providers": provider_rows,
        }
