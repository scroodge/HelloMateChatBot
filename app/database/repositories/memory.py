"""Conversation memory persistence repository."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import insert, select

from app.database.schema import conversation_messages, conversation_summaries
from app.database.util import upsert
from app.models.memory import ConversationMessage, ConversationSummary

if TYPE_CHECKING:
    from app.database.db import Database


class MemoryRepository(Protocol):
    """Persistence contract for conversation memory."""

    def add_message(self, message: ConversationMessage) -> ConversationMessage: ...

    def list_messages(self, user_id: int, limit: int = 20) -> list[ConversationMessage]: ...

    def get_summary(self, user_id: int) -> ConversationSummary | None: ...

    def set_summary(self, summary: ConversationSummary) -> ConversationSummary: ...


class MemoryRepositoryImpl:
    """SQLAlchemy implementation of MemoryRepository."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def add_message(self, message: ConversationMessage) -> ConversationMessage:
        with self._db.engine.begin() as connection:
            result = connection.execute(
                insert(conversation_messages).values(
                    user_id=message.user_id,
                    role=message.role,
                    content=message.content,
                    created_at=message.created_at.isoformat(),
                )
            )
            message_id = int(result.inserted_primary_key[0])
        return ConversationMessage(
            id=message_id,
            user_id=message.user_id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
        )

    def list_messages(self, user_id: int, limit: int = 20) -> list[ConversationMessage]:
        with self._db.engine.connect() as connection:
            rows = connection.execute(
                select(conversation_messages)
                .where(conversation_messages.c.user_id == user_id)
                .order_by(conversation_messages.c.id.desc())
                .limit(limit)
            ).all()
        messages = [
            ConversationMessage(
                id=int(row.id),
                user_id=int(row.user_id),
                role=row.role,
                content=row.content,
                created_at=datetime.fromisoformat(row.created_at),
            )
            for row in rows
        ]
        messages.reverse()
        return messages

    def get_summary(self, user_id: int) -> ConversationSummary | None:
        with self._db.engine.connect() as connection:
            row = connection.execute(
                select(conversation_summaries).where(conversation_summaries.c.user_id == user_id)
            ).first()
        if row is None:
            return None
        return ConversationSummary(
            user_id=int(row.user_id),
            summary=row.summary,
            updated_at=datetime.fromisoformat(row.updated_at),
        )

    def set_summary(self, summary: ConversationSummary) -> ConversationSummary:
        with self._db.engine.begin() as connection:
            upsert(
                connection,
                conversation_summaries,
                {
                    "user_id": summary.user_id,
                    "summary": summary.summary,
                    "updated_at": summary.updated_at.isoformat(),
                },
                index_elements=["user_id"],
                update_columns=["summary", "updated_at"],
            )
        return summary
