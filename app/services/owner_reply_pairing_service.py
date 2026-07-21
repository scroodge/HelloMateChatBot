"""Conservative, owner-reviewable draft-to-owner reply pairing (Phase 21A)."""

from __future__ import annotations

from datetime import timedelta

from app.database.repositories.owner_reply_pairs import OwnerReplyPairsRepository
from app.models.memory import ConversationMessage
from app.models.owner_reply_pair import OwnerReplyPair
from app.services.memory_service import MemoryService
from app.services.suggestions_service import SuggestionsService

PAIRING_WINDOW = timedelta(hours=2)


class OwnerReplyPairingService:
    def __init__(
        self,
        repository: OwnerReplyPairsRepository,
        suggestions_service: SuggestionsService,
        memory_service: MemoryService,
    ) -> None:
        self.repository = repository
        self.suggestions_service = suggestions_service
        self.memory_service = memory_service

    def observe_owner_reply(self, message: ConversationMessage) -> OwnerReplyPair | None:
        """Propose a pair only when the conversation could not have changed underneath it."""
        if message.id is None or not message.content.strip():
            return None
        candidates = [
            suggestion
            for suggestion in self.suggestions_service.list_pending()
            if suggestion.user_id == message.user_id
        ]
        if len(candidates) != 1:
            return None
        suggestion = candidates[0]
        if message.created_at - suggestion.created_at > PAIRING_WINDOW:
            return None
        if message.created_at < suggestion.created_at:
            return None
        if self.memory_service.has_contact_message_between(
            message.user_id, suggestion.created_at, message.created_at
        ):
            return None
        return self.repository.add(
            suggestion_id=suggestion.id,
            user_id=message.user_id,
            owner_message_id=message.id,
            owner_reply_text=message.content,
        )

    def list_pending(self) -> list[OwnerReplyPair]:
        return self.repository.list_pending()

    def list_reviewable(self) -> list[OwnerReplyPair]:
        return self.repository.list_reviewable()

    def get(self, pair_id: int) -> OwnerReplyPair | None:
        return self.repository.get(pair_id)

    def confirm(self, pair_id: int) -> bool:
        pair = self.repository.get(pair_id)
        if pair is None or pair.status != "pending":
            return False
        self.suggestions_service.mark_owner_reply(pair.suggestion_id, pair.owner_reply_text)
        self.repository.resolve(pair_id, "confirmed")
        return True

    def reject(self, pair_id: int, reason: str | None = None) -> bool:
        pair = self.repository.get(pair_id)
        if pair is None or pair.status != "pending":
            return False
        self.suggestions_service.dismiss(pair.suggestion_id, reason or "pair_rejected")
        self.repository.resolve(pair_id, "rejected", reason)
        return True

    def retract(self, pair_id: int, reason: str | None = None) -> bool:
        """Remove an already-confirmed pairing from feedback and future learning."""
        pair = self.repository.get(pair_id)
        if pair is None or pair.status != "confirmed":
            return False
        if not self.suggestions_service.retract_owner_reply(pair.suggestion_id):
            return False
        self.repository.retract(pair_id, reason or "owner_retracted_pair")
        return True
