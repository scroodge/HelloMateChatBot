"""Persistence for explicit owner-learning proposals."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import insert, select, update

from app.database.schema import learning_proposals
from app.models.learning_proposal import LearningProposal

if TYPE_CHECKING:
    from app.database.db import Database


class LearningProposalsRepositoryImpl:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(
        self, user_id: int, kind: str, payload: dict[str, str], evidence: dict[str, str]
    ) -> LearningProposal:
        now = datetime.now().astimezone()
        with self._db.engine.begin() as conn:
            result = conn.execute(
                insert(learning_proposals).values(
                    user_id=user_id,
                    kind=kind,
                    payload=json.dumps(payload, ensure_ascii=False),
                    evidence=json.dumps(evidence, ensure_ascii=False),
                    status="pending",
                    created_at=now.isoformat(),
                )
            )
        return LearningProposal(
            int(result.inserted_primary_key[0]), user_id, kind, payload, evidence, "pending", now
        )

    def get(self, proposal_id: int) -> LearningProposal | None:
        with self._db.engine.connect() as conn:
            row = conn.execute(
                select(learning_proposals).where(learning_proposals.c.id == proposal_id)
            ).first()
        return self._from_row(row) if row else None

    def list_reviewable(self) -> list[LearningProposal]:
        with self._db.engine.connect() as conn:
            rows = conn.execute(
                select(learning_proposals)
                .where(learning_proposals.c.status.in_(("pending", "approved")))
                .order_by(learning_proposals.c.created_at.desc())
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def resolve(self, proposal_id: int, status: str, applied_reference: str | None = None) -> None:
        with self._db.engine.begin() as conn:
            conn.execute(
                update(learning_proposals)
                .where(learning_proposals.c.id == proposal_id)
                .values(
                    status=status,
                    resolved_at=datetime.now().astimezone().isoformat(),
                    applied_reference=applied_reference,
                )
            )

    @staticmethod
    def _from_row(row: object) -> LearningProposal:
        return LearningProposal(
            id=int(row.id),
            user_id=int(row.user_id),
            kind=row.kind,
            payload=json.loads(row.payload),
            evidence=json.loads(row.evidence),
            status=row.status,
            created_at=datetime.fromisoformat(row.created_at),
            resolved_at=datetime.fromisoformat(row.resolved_at) if row.resolved_at else None,
            applied_reference=row.applied_reference,
        )
