"""Conversation memory persistence repository."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from app.models.memory import ConversationMessage, ConversationSummary

if TYPE_CHECKING:
    from app.database.sqlite import SQLiteDatabase


class MemoryRepository(Protocol):
    """Persistence contract for conversation memory."""

    def add_message(self, message: ConversationMessage) -> ConversationMessage: ...

    def list_messages(self, user_id: int, limit: int = 20) -> list[ConversationMessage]: ...

    def get_summary(self, user_id: int) -> ConversationSummary | None: ...

    def set_summary(self, summary: ConversationSummary) -> ConversationSummary: ...


class SQLiteMemoryRepository:
    """SQLite implementation of MemoryRepository."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def add_message(self, message: ConversationMessage) -> ConversationMessage:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO conversation_messages (user_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    message.user_id,
                    message.role,
                    message.content,
                    message.created_at.isoformat(),
                ),
            )
            message_id = int(cursor.lastrowid)
        return ConversationMessage(
            id=message_id,
            user_id=message.user_id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
        )

    def list_messages(self, user_id: int, limit: int = 20) -> list[ConversationMessage]:
        rows = self._database.connection.execute(
            """
            SELECT id, user_id, role, content, created_at
            FROM conversation_messages
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        messages = [
            ConversationMessage(
                id=int(row["id"]),
                user_id=int(row["user_id"]),
                role=row["role"],
                content=row["content"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]
        messages.reverse()
        return messages

    def get_summary(self, user_id: int) -> ConversationSummary | None:
        row = self._database.connection.execute(
            "SELECT user_id, summary, updated_at FROM conversation_summaries WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return ConversationSummary(
            user_id=int(row["user_id"]),
            summary=row["summary"],
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def set_summary(self, summary: ConversationSummary) -> ConversationSummary:
        with self._database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO conversation_summaries (user_id, summary, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    summary = excluded.summary,
                    updated_at = excluded.updated_at
                """,
                (
                    summary.user_id,
                    summary.summary,
                    summary.updated_at.isoformat(),
                ),
            )
        return summary
