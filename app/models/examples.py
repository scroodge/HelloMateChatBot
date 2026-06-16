"""Per-contact few-shot example models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ContactExample:
    """A curated (contact message -> reply) pair used as a few-shot guide.

    kind='positive': ideal reply to emulate.
    kind='negative': bad reply to avoid (anti-pattern).
    """

    user_id: int
    contact_message: str
    reply_text: str
    created_at: datetime
    id: int | None = None
    kind: str = "positive"
