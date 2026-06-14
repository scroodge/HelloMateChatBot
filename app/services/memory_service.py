"""Conversation memory business logic."""

from __future__ import annotations

from datetime import datetime

from app.database.repositories.memory import MemoryRepository
from app.models.memory import (
    ContactStyleProfile,
    ConversationMessage,
    ConversationSummary,
)


class MemoryService:
    """Store and retrieve conversation history."""

    def __init__(self, repository: MemoryRepository, window_size: int = 20) -> None:
        self.repository = repository
        self.window_size = window_size

    def record_user_message(
        self,
        user_id: int,
        content: str,
        now: datetime | None = None,
    ) -> ConversationMessage:
        """Persist a contact (incoming) message."""

        return self._record_message(user_id, "user", content, now, authored_by="contact")

    def record_assistant_message(
        self,
        user_id: int,
        content: str,
        now: datetime | None = None,
        authored_by: str = "bot",
    ) -> ConversationMessage:
        """Persist an assistant-side message.

        ``authored_by`` distinguishes a real owner reply ("owner", typed by the
        human in suggest/off mode) from an AI-generated one ("bot"). Only owner
        replies feed the style-learning profile.
        """

        return self._record_message(user_id, "assistant", content, now, authored_by=authored_by)

    def _record_message(
        self,
        user_id: int,
        role: str,
        content: str,
        now: datetime | None,
        authored_by: str | None = None,
    ) -> ConversationMessage:
        message = ConversationMessage(
            user_id=user_id,
            role=role,
            content=content,
            created_at=now or datetime.now().astimezone(),
            authored_by=authored_by,
        )
        return self.repository.add_message(message)

    def recent_messages(self, user_id: int) -> list[ConversationMessage]:
        """Return the latest message window for a user."""

        return self.repository.list_messages(user_id, limit=self.window_size)

    def get_summary(self, user_id: int) -> ConversationSummary | None:
        """Return a stored conversation summary."""

        return self.repository.get_summary(user_id)

    def set_summary(
        self,
        user_id: int,
        summary: str,
        covered_count: int = 0,
        now: datetime | None = None,
    ) -> ConversationSummary:
        """Persist a conversation summary and how many oldest messages it covers."""

        item = ConversationSummary(
            user_id=user_id,
            summary=summary,
            updated_at=now or datetime.now().astimezone(),
            covered_count=covered_count,
        )
        return self.repository.set_summary(item)

    def count_messages(self, user_id: int) -> int:
        """Total stored messages for a user."""

        return self.repository.count_messages(user_id)

    def messages_slice(
        self, user_id: int, *, offset: int, limit: int
    ) -> list[ConversationMessage]:
        """Return messages oldest-first within [offset, offset+limit)."""

        return self.repository.list_messages_asc(user_id, offset=offset, limit=limit)

    def count_owner_messages(self, user_id: int) -> int:
        """Total owner-authored (real human) replies for a contact."""

        return self.repository.count_owner_messages(user_id)

    def owner_messages_slice(
        self, user_id: int, *, offset: int, limit: int
    ) -> list[ConversationMessage]:
        """Return owner-authored messages oldest-first within [offset, offset+limit)."""

        return self.repository.list_owner_messages_asc(user_id, offset=offset, limit=limit)

    def get_style_profile(self, user_id: int) -> ContactStyleProfile | None:
        """Return the learned owner-style profile for a contact."""

        return self.repository.get_style_profile(user_id)

    def set_style_profile(
        self,
        user_id: int,
        profile: str,
        covered_count: int = 0,
        now: datetime | None = None,
    ) -> ContactStyleProfile:
        """Persist a learned owner-style profile for a contact."""

        item = ContactStyleProfile(
            user_id=user_id,
            profile=profile,
            updated_at=now or datetime.now().astimezone(),
            covered_count=covered_count,
        )
        return self.repository.set_style_profile(item)

    def delete_style_profile(self, user_id: int) -> None:
        """Remove the learned owner-style profile for a contact."""

        self.repository.delete_style_profile(user_id)

    def as_chat_messages(self, user_id: int) -> list[dict[str, str]]:
        """Return memory in LLM chat message format."""

        messages = self.recent_messages(user_id)
        return [{"role": message.role, "content": message.content} for message in messages]
