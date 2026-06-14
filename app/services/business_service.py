"""Telegram Business connection and managed-chat helpers."""

from __future__ import annotations

from datetime import datetime

from app.database.repositories.business import BusinessRepository
from app.models.business import BusinessChatRecord, BusinessConnectionRecord


class BusinessService:
    """Track business connections and resolve contacts in managed chats."""

    def __init__(self, repository: BusinessRepository) -> None:
        self.repository = repository

    def save_connection(
        self,
        *,
        connection_id: str,
        owner_user_id: int,
        is_enabled: bool,
        now: datetime | None = None,
    ) -> BusinessConnectionRecord:
        record = BusinessConnectionRecord(
            connection_id=connection_id,
            owner_user_id=owner_user_id,
            is_enabled=is_enabled,
            updated_at=now or datetime.now().astimezone(),
        )
        return self.repository.upsert_connection(record)

    def get_connection(self, connection_id: str) -> BusinessConnectionRecord | None:
        return self.repository.get_connection(connection_id)

    def get_connection_for_owner(self, owner_user_id: int) -> BusinessConnectionRecord | None:
        return self.repository.get_connection_for_owner(owner_user_id)

    def save_chat(
        self,
        *,
        chat_id: int,
        contact_user_id: int,
        connection_id: str,
        now: datetime | None = None,
    ) -> BusinessChatRecord:
        record = BusinessChatRecord(
            chat_id=chat_id,
            contact_user_id=contact_user_id,
            connection_id=connection_id,
            updated_at=now or datetime.now().astimezone(),
        )
        return self.repository.upsert_chat(record)

    def get_chat(self, chat_id: int) -> BusinessChatRecord | None:
        return self.repository.get_chat(chat_id)

    def get_chat_for_contact(self, contact_user_id: int) -> BusinessChatRecord | None:
        return self.repository.get_chat_for_contact(contact_user_id)

    @staticmethod
    def contact_user_id(chat_id: int) -> int:
        """Return the contact id for a managed private chat."""

        return chat_id

    @staticmethod
    def is_owner_message(owner_user_id: int, sender_user_id: int | None) -> bool:
        return sender_user_id is not None and sender_user_id == owner_user_id
