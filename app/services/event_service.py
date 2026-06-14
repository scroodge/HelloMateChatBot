"""Event recording service — thin layer over EventRepository.

Event types (string constants so callers don't hardcode strings):
  message_received   — user sent a text message
  ai_reply_sent      — bot replied via LLM
  greeting_sent      — proactive greeting delivered
  voice_transcribed  — voice message transcribed
  remember_saved     — /remember note stored
  mood_recorded      — /mood entry saved
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.database.repositories.events import EventRepository

logger = logging.getLogger(__name__)

MESSAGE_RECEIVED = "message_received"
AI_REPLY_SENT = "ai_reply_sent"
GREETING_SENT = "greeting_sent"
VOICE_TRANSCRIBED = "voice_transcribed"
REMEMBER_SAVED = "remember_saved"
MOOD_RECORDED = "mood_recorded"


class EventService:
    def __init__(self, repository: EventRepository) -> None:
        self._repo = repository

    def record(self, user_id: int, event_type: str, **meta) -> None:
        try:
            self._repo.record(user_id, event_type, meta or None)
        except Exception:
            logger.exception("Failed to record event %s for user %s", event_type, user_id)
