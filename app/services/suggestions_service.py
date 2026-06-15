"""Suggest inbox — persists drafted replies for owner review in the Mini App.

In suggest mode the bot already DMs the owner a draft with a copy button; this
service additionally stores the draft so the owner can review, edit, copy, save
as a few-shot example, or dismiss it from the Mini App. Each new draft for a
contact supersedes that contact's previous pending one (the conversation moved
on), keeping the inbox to the latest pending suggestion per contact.
"""

from __future__ import annotations

import logging

from app.database.repositories.suggestions import SuggestionsRepository
from app.models.suggestions import Suggestion

logger = logging.getLogger(__name__)

MAX_FIELD_CHARS = 2000


class SuggestionsService:
    def __init__(self, repository: SuggestionsRepository, *, enabled: bool = True) -> None:
        self.repository = repository
        self.enabled = enabled

    def record(self, user_id: int, contact_message: str, draft_text: str) -> Suggestion | None:
        """Persist a new pending suggestion, superseding the contact's prior one."""
        if not self.enabled:
            return None
        contact_message = (contact_message or "").strip()[:MAX_FIELD_CHARS]
        draft_text = (draft_text or "").strip()[:MAX_FIELD_CHARS]
        if not contact_message or not draft_text:
            return None
        try:
            self.repository.supersede_pending(user_id)
            return self.repository.add(user_id, contact_message, draft_text)
        except Exception:
            logger.exception("Failed to record suggestion for contact %s", user_id)
            return None

    def list_pending(self, limit: int = 100) -> list[Suggestion]:
        return self.repository.list_by_status("pending", limit=limit)

    def get(self, suggestion_id: int) -> Suggestion | None:
        return self.repository.get(suggestion_id)

    def dismiss(self, suggestion_id: int) -> None:
        self.repository.set_status(suggestion_id, "dismissed")

    def mark_saved(self, suggestion_id: int) -> None:
        self.repository.set_status(suggestion_id, "saved")

    def count_pending(self) -> int:
        return self.repository.count_by_status("pending")
