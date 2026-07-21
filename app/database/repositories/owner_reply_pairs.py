"""Persistence for reviewable draft-to-owner reply pairings."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import insert, select, update

from app.database.schema import owner_reply_pairs
from app.models.owner_reply_pair import OwnerReplyPair

class OwnerReplyPairsRepository(Protocol):
    def add(
        self,
        *,
        suggestion_id: int,
        user_id: int,
        owner_message_id: int,
        owner_reply_text: str,
    ) -> OwnerReplyPair: ...

    def list_pending(self, limit: int = 50) -> list[OwnerReplyPair]: ...

    def list_reviewable(self, limit: int = 50) -> list[OwnerReplyPair]: ...

    def get(self, pair_id: int) -> OwnerReplyPair | None: ...

    def resolve(self, pair_id: int, status: str, reason: str | None = None) -> None: ...

    def retract(self, pair_id: int, reason: str | None = None) -> None: ...


if TYPE_CHECKING:
    from app.database.db import Database


class OwnerReplyPairsRepositoryImpl(OwnerReplyPairsRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(
        self, *, suggestion_id: int, user_id: int, owner_message_id: int, owner_reply_text: str
    ) -> OwnerReplyPair:
        now = datetime.now().astimezone()
        values = {
            "suggestion_id": suggestion_id,
            "user_id": user_id,
            "owner_message_id": owner_message_id,
            "owner_reply_text": owner_reply_text,
            "confidence": 1.0,
            "status": "pending",
            "reason": None,
            "created_at": now.isoformat(),
            "resolved_at": None,
        }
        with self._db.engine.begin() as conn:
            result = conn.execute(insert(owner_reply_pairs).values(**values))
        return OwnerReplyPair(
            id=int(result.inserted_primary_key[0]),
            suggestion_id=suggestion_id,
            user_id=user_id,
            owner_message_id=owner_message_id,
            owner_reply_text=owner_reply_text,
            confidence=1.0,
            status="pending",
            reason=None,
            created_at=now,
            resolved_at=None,
        )

    def list_pending(self, limit: int = 50) -> list[OwnerReplyPair]:
        with self._db.engine.connect() as conn:
            rows = conn.execute(
                select(owner_reply_pairs)
                .where(owner_reply_pairs.c.status == "pending")
                .order_by(owner_reply_pairs.c.id.desc())
                .limit(limit)
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def list_reviewable(self, limit: int = 50) -> list[OwnerReplyPair]:
        with self._db.engine.connect() as conn:
            rows = conn.execute(
                select(owner_reply_pairs)
                .where(owner_reply_pairs.c.status.in_(("pending", "confirmed")))
                .order_by(owner_reply_pairs.c.id.desc())
                .limit(limit)
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def get(self, pair_id: int) -> OwnerReplyPair | None:
        with self._db.engine.connect() as conn:
            row = conn.execute(
                select(owner_reply_pairs).where(owner_reply_pairs.c.id == pair_id)
            ).first()
        return self._from_row(row) if row else None

    def resolve(self, pair_id: int, status: str, reason: str | None = None) -> None:
        with self._db.engine.begin() as conn:
            conn.execute(
                update(owner_reply_pairs)
                .where(owner_reply_pairs.c.id == pair_id, owner_reply_pairs.c.status == "pending")
                .values(
                    status=status,
                    reason=reason,
                    resolved_at=datetime.now().astimezone().isoformat(),
                )
            )

    def retract(self, pair_id: int, reason: str | None = None) -> None:
        with self._db.engine.begin() as conn:
            conn.execute(
                update(owner_reply_pairs)
                .where(owner_reply_pairs.c.id == pair_id, owner_reply_pairs.c.status == "confirmed")
                .values(
                    status="retracted",
                    reason=reason,
                    resolved_at=datetime.now().astimezone().isoformat(),
                )
            )

    @staticmethod
    def _from_row(row: object) -> OwnerReplyPair:
        return OwnerReplyPair(
            id=int(row.id), suggestion_id=int(row.suggestion_id), user_id=int(row.user_id),
            owner_message_id=int(row.owner_message_id), owner_reply_text=row.owner_reply_text,
            confidence=float(row.confidence), status=row.status, reason=row.reason,
            created_at=datetime.fromisoformat(row.created_at),
            resolved_at=datetime.fromisoformat(row.resolved_at) if row.resolved_at else None,
        )
