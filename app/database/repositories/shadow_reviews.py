"""Persistence for private, owner-triggered blind comparisons."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import insert, select, update

from app.database.schema import shadow_reviews
from app.models.shadow_review import ShadowReview

if TYPE_CHECKING:
    from app.database.db import Database


class ShadowReviewsRepositoryImpl:
    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, user_id: int, candidate_id: str, message_text: str) -> ShadowReview:
        now = datetime.now().astimezone().isoformat()
        with self._db.engine.begin() as conn:
            result = conn.execute(
                insert(shadow_reviews).values(
                    user_id=user_id,
                    candidate_id=candidate_id,
                    message_text=message_text,
                    status="queued",
                    created_at=now,
                )
            )
        review = self.get(int(result.inserted_primary_key[0]))
        assert review is not None
        return review

    def get(self, review_id: int) -> ShadowReview | None:
        with self._db.engine.connect() as conn:
            row = conn.execute(
                select(shadow_reviews).where(shadow_reviews.c.id == review_id)
            ).first()
        return self._from_row(row) if row else None

    def complete(self, review_id: int, reply_a: str, reply_b: str, mapping: str) -> None:
        with self._db.engine.begin() as conn:
            conn.execute(
                update(shadow_reviews)
                .where(shadow_reviews.c.id == review_id)
                .values(
                    reply_a=reply_a,
                    reply_b=reply_b,
                    mapping=mapping,
                    status="ready",
                    error=None,
                )
            )

    def fail(self, review_id: int, error: str) -> None:
        with self._db.engine.begin() as conn:
            conn.execute(
                update(shadow_reviews)
                .where(shadow_reviews.c.id == review_id)
                .values(status="failed", error=error[:500])
            )

    def resolve(self, review_id: int, winner: str) -> ShadowReview | None:
        if winner not in {"a", "b", "tie"}:
            raise ValueError("winner must be a, b, or tie")
        with self._db.engine.begin() as conn:
            conn.execute(
                update(shadow_reviews)
                .where(shadow_reviews.c.id == review_id, shadow_reviews.c.status == "ready")
                .values(
                    status="resolved",
                    winner=winner,
                    resolved_at=datetime.now().astimezone().isoformat(),
                )
            )
        return self.get(review_id)

    def recent(self, *, limit: int = 20) -> list[ShadowReview]:
        with self._db.engine.connect() as conn:
            rows = conn.execute(
                select(shadow_reviews)
                .order_by(shadow_reviews.c.id.desc())
                .limit(max(1, min(limit, 50)))
            ).all()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: object) -> ShadowReview:
        return ShadowReview(
            id=int(row.id), user_id=int(row.user_id), candidate_id=row.candidate_id,
            message_text=row.message_text, reply_a=row.reply_a, reply_b=row.reply_b,
            mapping=row.mapping, status=row.status, winner=row.winner,
            created_at=datetime.fromisoformat(row.created_at),
            resolved_at=datetime.fromisoformat(row.resolved_at) if row.resolved_at else None,
            error=row.error,
        )
