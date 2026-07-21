"""Repository for the suggest inbox."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, insert, select, update

from app.database.schema import suggestions
from app.models.suggestions import Suggestion

if TYPE_CHECKING:
    from app.database.db import Database


class SuggestionsRepository:
    def add(
        self,
        user_id: int,
        contact_message: str,
        draft_text: str,
        generation_trace_id: str | None = None,
    ) -> Suggestion:
        raise NotImplementedError

    def supersede_pending(self, user_id: int) -> list[int]:
        raise NotImplementedError

    def list_by_status(self, status: str, limit: int = 100) -> list[Suggestion]:
        raise NotImplementedError

    def get(self, suggestion_id: int) -> Suggestion | None:
        raise NotImplementedError

    def set_status(self, suggestion_id: int, status: str) -> None:
        raise NotImplementedError

    def count_by_status(self, status: str) -> int:
        raise NotImplementedError


class SuggestionsRepositoryImpl(SuggestionsRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    @staticmethod
    def _row_to_model(row) -> Suggestion:
        return Suggestion(
            id=int(row.id),
            user_id=int(row.user_id),
            contact_message=row.contact_message,
            draft_text=row.draft_text,
            status=row.status,
            created_at=datetime.fromisoformat(row.created_at),
            generation_trace_id=getattr(row, "generation_trace_id", None),
        )

    def add(
        self,
        user_id: int,
        contact_message: str,
        draft_text: str,
        generation_trace_id: str | None = None,
    ) -> Suggestion:
        now = datetime.now().astimezone()
        with self._db.engine.begin() as conn:
            result = conn.execute(
                insert(suggestions).values(
                    user_id=user_id,
                    contact_message=contact_message,
                    draft_text=draft_text,
                    status="pending",
                    generation_trace_id=generation_trace_id,
                    created_at=now.isoformat(),
                )
            )
            new_id = int(result.inserted_primary_key[0])
        return Suggestion(
            id=new_id,
            user_id=user_id,
            contact_message=contact_message,
            draft_text=draft_text,
            status="pending",
            created_at=now,
            generation_trace_id=generation_trace_id,
        )

    def supersede_pending(self, user_id: int) -> list[int]:
        with self._db.engine.begin() as conn:
            ids = [
                int(row.id)
                for row in conn.execute(
                    select(suggestions.c.id).where(
                        suggestions.c.user_id == user_id, suggestions.c.status == "pending"
                    )
                )
            ]
            conn.execute(
                update(suggestions)
                .where(suggestions.c.user_id == user_id, suggestions.c.status == "pending")
                .values(status="superseded")
            )
        return ids

    def list_by_status(self, status: str, limit: int = 100) -> list[Suggestion]:
        with self._db.engine.connect() as conn:
            rows = conn.execute(
                select(suggestions)
                .where(suggestions.c.status == status)
                .order_by(suggestions.c.id.desc())
                .limit(limit)
            ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def get(self, suggestion_id: int) -> Suggestion | None:
        with self._db.engine.connect() as conn:
            row = conn.execute(
                select(suggestions).where(suggestions.c.id == suggestion_id)
            ).fetchone()
        return self._row_to_model(row) if row is not None else None

    def set_status(self, suggestion_id: int, status: str) -> None:
        with self._db.engine.begin() as conn:
            conn.execute(
                update(suggestions).where(suggestions.c.id == suggestion_id).values(status=status)
            )

    def count_by_status(self, status: str) -> int:
        with self._db.engine.connect() as conn:
            return int(
                conn.execute(
                    select(func.count())
                    .select_from(suggestions)
                    .where(suggestions.c.status == status)
                ).scalar_one()
            )
