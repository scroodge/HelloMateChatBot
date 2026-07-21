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
    source_message_id: int | None = None
    confidence: float | None = None
    first_observed_at: datetime | None = None
    last_observed_at: datetime | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    owner_confirmed: bool = False
    version_id: str | None = None


@dataclass(frozen=True, slots=True)
class ContactFactHistory:
    """An inactive version of a fact kept for provenance and conflict review."""

    id: int
    user_id: int
    key: str
    value: str
    source_message_id: int | None
    confidence: float | None
    first_observed_at: datetime | None
    last_observed_at: datetime | None
    valid_from: datetime | None
    valid_until: datetime | None
    owner_confirmed: bool
    version_id: str | None
    superseded_by: str | None


@dataclass(frozen=True, slots=True)
class ContactFactsMeta:
    """Extraction-state record: how many messages existed at last extraction."""

    user_id: int
    last_message_count: int
    updated_at: datetime
