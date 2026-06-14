"""Per-contact durable fact models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ContactFact:
    """A single stable fact extracted from a conversation with a contact."""

    user_id: int
    key: str
    value: str
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ContactFactsMeta:
    """Extraction-state record: how many messages existed at last extraction."""

    user_id: int
    last_message_count: int
    updated_at: datetime
