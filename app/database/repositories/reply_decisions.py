"""Persistence for shadow-only reply risk decisions."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import insert, select

from app.database.schema import reply_decisions
from app.models.reply_decision import ReplyDecision

if TYPE_CHECKING:
    from app.database.db import Database


class ReplyDecisionsRepositoryImpl:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, user_id: int, actual_mode: str, decision: ReplyDecision) -> None:
        with self._db.engine.begin() as conn:
            conn.execute(
                insert(reply_decisions).values(
                    user_id=user_id,
                    intent=decision.intent,
                    risk_level=decision.risk_level,
                    memory_confidence=decision.memory_confidence,
                    requires_owner_knowledge=decision.requires_owner_knowledge,
                    requires_external_action=decision.requires_external_action,
                    recommended_mode=decision.recommended_mode,
                    actual_mode=actual_mode,
                    reasons=json.dumps(decision.reasons, ensure_ascii=False),
                    created_at=datetime.now().astimezone().isoformat(),
                )
            )

    def recent(self, *, limit: int = 50) -> list[dict[str, object]]:
        with self._db.engine.connect() as conn:
            rows = conn.execute(
                select(reply_decisions)
                .order_by(reply_decisions.c.id.desc())
                .limit(max(1, min(limit, 100)))
            ).mappings().all()
        return [
            {
                **dict(row),
                "reasons": json.loads(str(row["reasons"])),
                "is_divergent": row["actual_mode"] != row["recommended_mode"],
            }
            for row in rows
        ]
