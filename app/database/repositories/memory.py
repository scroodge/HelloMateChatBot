"""Conversation memory persistence repository."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import delete, func, insert, select

from app.database.schema import (
    contact_style_profiles,
    conversation_messages,
    conversation_summaries,
)
from app.database.util import upsert
from app.models.memory import (
    ContactStyleProfile,
    ConversationMessage,
    ConversationSummary,
)

if TYPE_CHECKING:
    from app.database.db import Database


class MemoryRepository(Protocol):
    """Persistence contract for conversation memory."""

    def add_message(self, message: ConversationMessage) -> ConversationMessage: ...

    def list_messages(self, user_id: int, limit: int = 20) -> list[ConversationMessage]: ...

    def count_messages(self, user_id: int) -> int: ...

    def list_messages_asc(
        self, user_id: int, *, offset: int, limit: int
    ) -> list[ConversationMessage]: ...

    def count_owner_messages(self, user_id: int) -> int: ...

    def list_owner_messages_asc(
        self, user_id: int, *, offset: int, limit: int
    ) -> list[ConversationMessage]: ...

    def get_summary(self, user_id: int) -> ConversationSummary | None: ...

    def set_summary(self, summary: ConversationSummary) -> ConversationSummary: ...

    def get_style_profile(self, user_id: int) -> ContactStyleProfile | None: ...

    def set_style_profile(self, profile: ContactStyleProfile) -> ContactStyleProfile: ...

    def delete_style_profile(self, user_id: int) -> None: ...


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
                    authored_by=message.authored_by,
                )
            )
            message_id = int(result.inserted_primary_key[0])
        return ConversationMessage(
            id=message_id,
            user_id=message.user_id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
            authored_by=message.authored_by,
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
                authored_by=getattr(row, "authored_by", None),
            )
            for row in rows
        ]
        messages.reverse()
        return messages

    def count_owner_messages(self, user_id: int) -> int:
        with self._db.engine.connect() as connection:
            return int(
                connection.execute(
                    select(func.count())
                    .select_from(conversation_messages)
                    .where(
                        conversation_messages.c.user_id == user_id,
                        conversation_messages.c.authored_by == "owner",
                    )
                ).scalar_one()
            )

    def list_owner_messages_asc(
        self, user_id: int, *, offset: int, limit: int
    ) -> list[ConversationMessage]:
        with self._db.engine.connect() as connection:
            rows = connection.execute(
                select(conversation_messages)
                .where(
                    conversation_messages.c.user_id == user_id,
                    conversation_messages.c.authored_by == "owner",
                )
                .order_by(conversation_messages.c.id.asc())
                .offset(offset)
                .limit(limit)
            ).all()
        return [
            ConversationMessage(
                id=int(row.id),
                user_id=int(row.user_id),
                role=row.role,
                content=row.content,
                created_at=datetime.fromisoformat(row.created_at),
                authored_by=getattr(row, "authored_by", None),
            )
            for row in rows
        ]

    def count_messages(self, user_id: int) -> int:
        with self._db.engine.connect() as connection:
            return int(
                connection.execute(
                    select(func.count())
                    .select_from(conversation_messages)
                    .where(conversation_messages.c.user_id == user_id)
                ).scalar_one()
            )

    def list_messages_asc(
        self, user_id: int, *, offset: int, limit: int
    ) -> list[ConversationMessage]:
        with self._db.engine.connect() as connection:
            rows = connection.execute(
                select(conversation_messages)
                .where(conversation_messages.c.user_id == user_id)
                .order_by(conversation_messages.c.id.asc())
                .offset(offset)
                .limit(limit)
            ).all()
        return [
            ConversationMessage(
                id=int(row.id),
                user_id=int(row.user_id),
                role=row.role,
                content=row.content,
                created_at=datetime.fromisoformat(row.created_at),
                authored_by=getattr(row, "authored_by", None),
            )
            for row in rows
        ]

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
            covered_count=int(getattr(row, "covered_count", 0) or 0),
        )

    def set_summary(self, summary: ConversationSummary) -> ConversationSummary:
        with self._db.engine.begin() as connection:
            upsert(
                connection,
                conversation_summaries,
                {
                    "user_id": summary.user_id,
                    "summary": summary.summary,
                    "covered_count": summary.covered_count,
                    "updated_at": summary.updated_at.isoformat(),
                },
                index_elements=["user_id"],
                update_columns=["summary", "covered_count", "updated_at"],
            )
        return summary

    def get_style_profile(self, user_id: int) -> ContactStyleProfile | None:
        with self._db.engine.connect() as connection:
            row = connection.execute(
                select(contact_style_profiles).where(
                    contact_style_profiles.c.user_id == user_id
                )
            ).first()
        if row is None:
            return None
        return ContactStyleProfile(
            user_id=int(row.user_id),
            profile=row.profile,
            updated_at=datetime.fromisoformat(row.updated_at),
            covered_count=int(getattr(row, "covered_count", 0) or 0),
        )

    def set_style_profile(self, profile: ContactStyleProfile) -> ContactStyleProfile:
        with self._db.engine.begin() as connection:
            upsert(
                connection,
                contact_style_profiles,
                {
                    "user_id": profile.user_id,
                    "profile": profile.profile,
                    "covered_count": profile.covered_count,
                    "updated_at": profile.updated_at.isoformat(),
                },
                index_elements=["user_id"],
                update_columns=["profile", "covered_count", "updated_at"],
            )
        return profile

    def delete_style_profile(self, user_id: int) -> None:
        with self._db.engine.begin() as connection:
            connection.execute(
                delete(contact_style_profiles).where(
                    contact_style_profiles.c.user_id == user_id
                )
            )
