"""Conversation memory persistence repository."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import and_, delete, func, insert, or_, select

from app.database.schema import (
    contact_style_profiles,
    conversation_message_embeddings,
    conversation_messages,
    conversation_summaries,
    owner_style_profiles,
    recall_index_meta,
)
from app.database.util import upsert
from app.models.memory import (
    ContactStyleProfile,
    ConversationMessage,
    ConversationSummary,
    OwnerStyleProfile,
)

if TYPE_CHECKING:
    from app.database.db import Database


class MemoryRepository(Protocol):
    """Persistence contract for conversation memory."""

    def add_message(self, message: ConversationMessage) -> ConversationMessage: ...

    def list_messages(self, user_id: int, limit: int = 20) -> list[ConversationMessage]: ...

    def count_messages(self, user_id: int) -> int: ...

    def clear_messages(self, user_id: int) -> None: ...

    def list_messages_asc(
        self, user_id: int, *, offset: int, limit: int
    ) -> list[ConversationMessage]: ...

    def list_messages_before(
        self, user_id: int, *, before_id: int | None, limit: int
    ) -> tuple[list[ConversationMessage], bool]: ...

    def count_owner_messages(self, user_id: int) -> int: ...

    def list_owner_messages_asc(
        self, user_id: int, *, offset: int, limit: int
    ) -> list[ConversationMessage]: ...

    def list_owner_messages_after_id(
        self, user_ids: set[int], *, after_id: int, limit: int
    ) -> list[ConversationMessage]: ...

    def get_summary(self, user_id: int) -> ConversationSummary | None: ...

    def set_summary(self, summary: ConversationSummary) -> ConversationSummary: ...

    def delete_summary(self, user_id: int) -> None: ...

    def get_style_profile(self, user_id: int) -> ContactStyleProfile | None: ...

    def set_style_profile(self, profile: ContactStyleProfile) -> ContactStyleProfile: ...

    def delete_style_profile(self, user_id: int) -> None: ...

    def get_owner_style_profile(self, scope_key: str) -> OwnerStyleProfile | None: ...

    def set_owner_style_profile(self, profile: OwnerStyleProfile) -> OwnerStyleProfile: ...

    def add_message_embedding(self, message_id: int, user_id: int, embedding: bytes) -> None: ...

    def get_recall_watermark(self, user_id: int) -> int: ...

    def set_recall_watermark(self, user_id: int, watermark_id: int) -> None: ...

    def list_unindexed_messages(
        self, user_id: int, after_id: int, limit: int, min_chars: int
    ) -> list[ConversationMessage]: ...

    def list_embeddings_for_user(self, user_id: int) -> list[tuple[int, bytes]]: ...

    def recall_index_stats(self) -> tuple[int, int]: ...

    def list_messages_by_ids(
        self, user_id: int, message_ids: set[int]
    ) -> list[ConversationMessage]: ...

    def has_contact_message_between(
        self, user_id: int, after: datetime, before: datetime
    ) -> bool: ...


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

    def list_owner_messages_after_id(
        self, user_ids: set[int], *, after_id: int, limit: int
    ) -> list[ConversationMessage]:
        if not user_ids:
            return []
        with self._db.engine.connect() as connection:
            rows = connection.execute(
                select(conversation_messages)
                .where(
                    conversation_messages.c.user_id.in_(user_ids),
                    conversation_messages.c.authored_by == "owner",
                    conversation_messages.c.id > after_id,
                )
                .order_by(conversation_messages.c.id.asc())
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

    def has_contact_message_between(self, user_id: int, after: datetime, before: datetime) -> bool:
        with self._db.engine.connect() as connection:
            row = connection.execute(
                select(conversation_messages.c.id)
                .where(
                    conversation_messages.c.user_id == user_id,
                    conversation_messages.c.created_at > after.isoformat(),
                    conversation_messages.c.created_at <= before.isoformat(),
                    or_(
                        conversation_messages.c.authored_by == "contact",
                        and_(
                            conversation_messages.c.authored_by.is_(None),
                            conversation_messages.c.role == "user",
                        ),
                    ),
                )
                .limit(1)
            ).first()
        return row is not None

    def clear_messages(self, user_id: int) -> None:
        with self._db.engine.begin() as connection:
            connection.execute(
                delete(conversation_messages).where(conversation_messages.c.user_id == user_id)
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

    def list_messages_before(
        self, user_id: int, *, before_id: int | None, limit: int
    ) -> tuple[list[ConversationMessage], bool]:
        query = select(conversation_messages).where(conversation_messages.c.user_id == user_id)
        if before_id is not None:
            query = query.where(conversation_messages.c.id < before_id)
        query = query.order_by(conversation_messages.c.id.desc()).limit(limit + 1)

        with self._db.engine.connect() as connection:
            rows = connection.execute(query).all()

        has_more = len(rows) > limit
        rows = rows[:limit]
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
        return messages, has_more

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

    def delete_summary(self, user_id: int) -> None:
        with self._db.engine.begin() as connection:
            connection.execute(
                delete(conversation_summaries).where(conversation_summaries.c.user_id == user_id)
            )

    def get_style_profile(self, user_id: int) -> ContactStyleProfile | None:
        with self._db.engine.connect() as connection:
            row = connection.execute(
                select(contact_style_profiles).where(contact_style_profiles.c.user_id == user_id)
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
                delete(contact_style_profiles).where(contact_style_profiles.c.user_id == user_id)
            )

    def get_owner_style_profile(self, scope_key: str) -> OwnerStyleProfile | None:
        with self._db.engine.connect() as connection:
            row = connection.execute(
                select(owner_style_profiles).where(owner_style_profiles.c.scope_key == scope_key)
            ).first()
        if row is None:
            return None
        return OwnerStyleProfile(
            scope_key=row.scope_key,
            profile=row.profile,
            updated_at=datetime.fromisoformat(row.updated_at),
            covered_through_message_id=int(row.covered_through_message_id or 0),
        )

    def set_owner_style_profile(self, profile: OwnerStyleProfile) -> OwnerStyleProfile:
        with self._db.engine.begin() as connection:
            upsert(
                connection,
                owner_style_profiles,
                {
                    "scope_key": profile.scope_key,
                    "profile": profile.profile,
                    "covered_through_message_id": profile.covered_through_message_id,
                    "updated_at": profile.updated_at.isoformat(),
                },
                index_elements=["scope_key"],
                update_columns=["profile", "covered_through_message_id", "updated_at"],
            )
        return profile

    def add_message_embedding(self, message_id: int, user_id: int, embedding: bytes) -> None:
        with self._db.engine.begin() as connection:
            dialect = connection.engine.dialect.name
            if dialect == "postgresql":
                from sqlalchemy.dialects.postgresql import insert as pg_insert

                stmt = pg_insert(conversation_message_embeddings).values(
                    message_id=message_id, user_id=user_id, embedding=embedding
                )
                stmt = stmt.on_conflict_do_nothing(index_elements=["message_id"])
            else:
                from sqlalchemy.dialects.sqlite import insert as sqlite_insert

                stmt = sqlite_insert(conversation_message_embeddings).values(
                    message_id=message_id, user_id=user_id, embedding=embedding
                )
                stmt = stmt.on_conflict_do_nothing(index_elements=["message_id"])
            connection.execute(stmt)

    def get_recall_watermark(self, user_id: int) -> int:
        with self._db.engine.connect() as connection:
            row = connection.execute(
                select(recall_index_meta.c.watermark_id).where(
                    recall_index_meta.c.user_id == user_id
                )
            ).first()
        return int(row.watermark_id) if row is not None else 0

    def set_recall_watermark(self, user_id: int, watermark_id: int) -> None:
        with self._db.engine.begin() as connection:
            upsert(
                connection,
                recall_index_meta,
                {
                    "user_id": user_id,
                    "watermark_id": watermark_id,
                    "updated_at": datetime.now().isoformat(),
                },
                index_elements=["user_id"],
                update_columns=["watermark_id", "updated_at"],
            )

    def list_unindexed_messages(
        self, user_id: int, after_id: int, limit: int, min_chars: int
    ) -> list[ConversationMessage]:
        with self._db.engine.connect() as connection:
            rows = connection.execute(
                select(conversation_messages)
                .where(
                    conversation_messages.c.user_id == user_id,
                    conversation_messages.c.id > after_id,
                    conversation_messages.c.role == "user",
                    func.length(conversation_messages.c.content) >= min_chars,
                )
                .order_by(conversation_messages.c.id.asc())
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

    def list_embeddings_for_user(self, user_id: int) -> list[tuple[int, bytes]]:
        with self._db.engine.connect() as connection:
            rows = connection.execute(
                select(
                    conversation_message_embeddings.c.message_id,
                    conversation_message_embeddings.c.embedding,
                ).where(conversation_message_embeddings.c.user_id == user_id)
            ).all()
        return [(int(row.message_id), row.embedding) for row in rows]

    def recall_index_stats(self) -> tuple[int, int]:
        """Return (total embeddings, number of distinct indexed contacts)."""
        with self._db.engine.connect() as connection:
            total = int(
                connection.execute(
                    select(func.count()).select_from(conversation_message_embeddings)
                ).scalar_one()
            )
            contacts = int(
                connection.execute(
                    select(func.count(func.distinct(conversation_message_embeddings.c.user_id)))
                ).scalar_one()
            )
        return total, contacts

    def list_messages_by_ids(
        self, user_id: int, message_ids: set[int]
    ) -> list[ConversationMessage]:
        if not message_ids:
            return []
        with self._db.engine.connect() as connection:
            rows = connection.execute(
                select(conversation_messages).where(
                    conversation_messages.c.user_id == user_id,
                    conversation_messages.c.id.in_(message_ids),
                )
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
