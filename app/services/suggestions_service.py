"""Suggest inbox — persists drafted replies for owner review in the Mini App.

In suggest mode the bot already DMs the owner a draft with a copy button; this
service additionally stores the draft so the owner can review, edit, copy, save
as a few-shot example, or dismiss it from the Mini App. Each new draft for a
contact supersedes that contact's previous pending one (the conversation moved
on), keeping the inbox to the latest pending suggestion per contact.
"""

from __future__ import annotations

import logging
from datetime import datetime
from difflib import SequenceMatcher

from app.database.repositories.suggestions import SuggestionsRepository
from app.models.suggestions import Suggestion

logger = logging.getLogger(__name__)

MAX_FIELD_CHARS = 2000


class SuggestionsService:
    def __init__(
        self,
        repository: SuggestionsRepository,
        feedback_repository: object | None = None,
        *,
        enabled: bool = True,
    ) -> None:
        self.repository = repository
        self.feedback_repository = feedback_repository
        self.enabled = enabled

    def record(
        self,
        user_id: int,
        contact_message: str,
        draft_text: str,
        generation_trace_id: str | None = None,
    ) -> Suggestion | None:
        """Persist a new pending suggestion, superseding the contact's prior one."""
        if not self.enabled:
            return None
        contact_message = (contact_message or "").strip()[:MAX_FIELD_CHARS]
        draft_text = (draft_text or "").strip()[:MAX_FIELD_CHARS]
        if not contact_message or not draft_text:
            return None
        try:
            for suggestion_id in self.repository.supersede_pending(user_id):
                self._event(suggestion_id, "superseded")
            suggestion = self.repository.add(
                user_id, contact_message, draft_text, generation_trace_id
            )
            self._event(suggestion.id, "suggestion_created")
            if generation_trace_id and self.feedback_repository is not None:
                self.feedback_repository.link_generation_run(generation_trace_id, suggestion.id)
            return suggestion
        except Exception:
            logger.exception("Failed to record suggestion for contact %s", user_id)
            return None

    def list_pending(self, limit: int = 100) -> list[Suggestion]:
        return self.repository.list_by_status("pending", limit=limit)

    def get(self, suggestion_id: int) -> Suggestion | None:
        return self.repository.get(suggestion_id)

    def dismiss(self, suggestion_id: int, reason: str | None = None) -> None:
        self.repository.set_status(suggestion_id, "dismissed")
        self._event(suggestion_id, "dismissed", reason)

    def mark_saved(
        self,
        suggestion_id: int,
        *,
        kind: str = "positive",
        final_text: str | None = None,
        reason: str | None = None,
    ) -> None:
        suggestion = self.get(suggestion_id)
        if suggestion is None:
            return
        self.repository.set_status(suggestion_id, "saved")
        self._event(
            suggestion_id, "saved_positive" if kind == "positive" else "saved_negative", reason
        )
        if kind == "positive":
            self._record_decision(suggestion, final_text or suggestion.draft_text, reason)

    def copied(self, suggestion_id: int) -> None:
        self._event(suggestion_id, "copied")

    def viewed(self, suggestion_id: int) -> None:
        self._event(suggestion_id, "viewed")

    def accept(self, suggestion_id: int, final_text: str, reason: str | None = None) -> None:
        suggestion = self.get(suggestion_id)
        if suggestion is None:
            return
        self.repository.set_status(suggestion_id, "accepted")
        self._record_decision(suggestion, final_text, reason)

    def owner_replied(self, user_id: int, final_text: str) -> None:
        for suggestion in self.list_pending():
            if suggestion.user_id == user_id:
                self.repository.set_status(suggestion.id, "owner_replied")
                self._record_decision(suggestion, final_text, None, event_type="owner_replied")

    def _record_decision(
        self,
        suggestion: Suggestion,
        final_text: str,
        reason: str | None,
        *,
        event_type: str | None = None,
    ) -> None:
        final_text = final_text.strip()[:MAX_FIELD_CHARS]
        if not final_text:
            return
        event_type = event_type or (
            "accepted_as_is" if final_text == suggestion.draft_text else "accepted_edited"
        )
        self._event(suggestion.id, event_type, reason)
        if self.feedback_repository is not None:
            created_at = suggestion.created_at
            seconds = max(0, round((datetime.now(created_at.tzinfo) - created_at).total_seconds()))
            self.feedback_repository.save_outcome(
                suggestion.id,
                final_text,
                _levenshtein(suggestion.draft_text, final_text),
                _token_distance(suggestion.draft_text, final_text),
                SequenceMatcher(None, suggestion.draft_text, final_text).ratio(),
                seconds,
            )

    def _event(self, suggestion_id: int | None, event_type: str, reason: str | None = None) -> None:
        if suggestion_id is not None and self.feedback_repository is not None:
            self.feedback_repository.add_feedback_event(suggestion_id, event_type, reason=reason)

    def count_pending(self) -> int:
        return self.repository.count_by_status("pending")


def _levenshtein(left: str, right: str) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, 1):
        current = [i]
        for j, right_char in enumerate(right, 1):
            current.append(
                min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (left_char != right_char))
            )
        previous = current
    return previous[-1]


def _token_distance(left: str, right: str) -> int:
    return _levenshtein(left.split(), right.split())
