"""Conversation memory business logic."""

from __future__ import annotations

from datetime import datetime

from app.database.repositories.memory import MemoryRepository
from app.models.memory import ConversationMessage, ConversationSummary


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
        """Persist a user message."""

        return self._record_message(user_id, "user", content, now)

    def record_assistant_message(
        self,
        user_id: int,
        content: str,
        now: datetime | None = None,
    ) -> ConversationMessage:
        """Persist an assistant message."""

        return self._record_message(user_id, "assistant", content, now)

    def _record_message(
        self,
        user_id: int,
        role: str,
        content: str,
        now: datetime | None,
    ) -> ConversationMessage:
        message = ConversationMessage(
            user_id=user_id,
            role=role,
            content=content,
            created_at=now or datetime.now().astimezone(),
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
        now: datetime | None = None,
    ) -> ConversationSummary:
        """Persist a conversation summary."""

        item = ConversationSummary(
            user_id=user_id,
            summary=summary,
            updated_at=now or datetime.now().astimezone(),
        )
        return self.repository.set_summary(item)

    def as_chat_messages(self, user_id: int) -> list[dict[str, str]]:
        """Return memory in LLM chat message format."""

        messages = self.recent_messages(user_id)
        return [{"role": message.role, "content": message.content} for message in messages]
