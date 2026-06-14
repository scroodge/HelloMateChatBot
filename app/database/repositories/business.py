"""Telegram Business connection persistence."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import select

from app.database.schema import business_chats, business_connections
from app.database.util import upsert
from app.models.business import BusinessChatRecord, BusinessConnectionRecord

if TYPE_CHECKING:
    from app.database.db import Database


class BusinessRepository(Protocol):
    """Persistence contract for Telegram Business state."""

    def upsert_connection(self, record: BusinessConnectionRecord) -> BusinessConnectionRecord: ...

    def get_connection(self, connection_id: str) -> BusinessConnectionRecord | None: ...

    def get_connection_for_owner(self, owner_user_id: int) -> BusinessConnectionRecord | None: ...

    def upsert_chat(self, record: BusinessChatRecord) -> BusinessChatRecord: ...

    def get_chat(self, chat_id: int) -> BusinessChatRecord | None: ...

    def get_chat_for_contact(self, contact_user_id: int) -> BusinessChatRecord | None: ...


class BusinessRepositoryImpl:
    """SQLAlchemy implementation of BusinessRepository."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def upsert_connection(self, record: BusinessConnectionRecord) -> BusinessConnectionRecord:
        with self._db.engine.begin() as connection:
            upsert(
                connection,
                business_connections,
                {
                    "connection_id": record.connection_id,
                    "owner_user_id": record.owner_user_id,
                    "is_enabled": record.is_enabled,
                    "updated_at": record.updated_at.isoformat(),
                },
                index_elements=["connection_id"],
                update_columns=["owner_user_id", "is_enabled", "updated_at"],
            )
        return record

    def get_connection(self, connection_id: str) -> BusinessConnectionRecord | None:
        with self._db.engine.connect() as connection:
            row = connection.execute(
                select(business_connections).where(
                    business_connections.c.connection_id == connection_id
                )
            ).first()
        if row is None:
            return None
        return self._row_to_connection(row)

    def get_connection_for_owner(self, owner_user_id: int) -> BusinessConnectionRecord | None:
        with self._db.engine.connect() as connection:
            row = (
                connection.execute(
                    select(business_connections)
                    .where(business_connections.c.owner_user_id == owner_user_id)
                    .where(business_connections.c.is_enabled.is_(True))
                    .order_by(business_connections.c.updated_at.desc())
                )
                .first()
            )
        if row is None:
            return None
        return self._row_to_connection(row)

    def upsert_chat(self, record: BusinessChatRecord) -> BusinessChatRecord:
        with self._db.engine.begin() as connection:
            upsert(
                connection,
                business_chats,
                {
                    "chat_id": record.chat_id,
                    "contact_user_id": record.contact_user_id,
                    "connection_id": record.connection_id,
                    "updated_at": record.updated_at.isoformat(),
                },
                index_elements=["chat_id"],
                update_columns=["contact_user_id", "connection_id", "updated_at"],
            )
        return record

    def get_chat(self, chat_id: int) -> BusinessChatRecord | None:
        with self._db.engine.connect() as connection:
            row = connection.execute(
                select(business_chats).where(business_chats.c.chat_id == chat_id)
            ).first()
        if row is None:
            return None
        return self._row_to_chat(row)

    def get_chat_for_contact(self, contact_user_id: int) -> BusinessChatRecord | None:
        with self._db.engine.connect() as connection:
            row = (
                connection.execute(
                    select(business_chats)
                    .where(business_chats.c.contact_user_id == contact_user_id)
                    .order_by(business_chats.c.updated_at.desc())
                )
                .first()
            )
        if row is None:
            return None
        return self._row_to_chat(row)

    @staticmethod
    def _row_to_connection(row: object) -> BusinessConnectionRecord:
        return BusinessConnectionRecord(
            connection_id=row.connection_id,
            owner_user_id=int(row.owner_user_id),
            is_enabled=bool(row.is_enabled),
            updated_at=datetime.fromisoformat(row.updated_at),
        )

    @staticmethod
    def _row_to_chat(row: object) -> BusinessChatRecord:
        return BusinessChatRecord(
            chat_id=int(row.chat_id),
            contact_user_id=int(row.contact_user_id),
            connection_id=row.connection_id,
            updated_at=datetime.fromisoformat(row.updated_at),
        )
