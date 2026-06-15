"""Per-contact few-shot example models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ContactExample:
    """A curated (contact message -> ideal reply) pair used as a few-shot guide."""

    user_id: int
    contact_message: str
    reply_text: str
    created_at: datetime
    id: int | None = None
