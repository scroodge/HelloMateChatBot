"""Conversation memory models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    """A stored chat message."""

    user_id: int
    role: str
    content: str
    created_at: datetime
    id: int | None = None
    # who actually authored the text: "contact", "owner" (real human reply), or
    # "bot" (AI-generated). Legacy rows are NULL/None.
    authored_by: str | None = None


@dataclass(frozen=True, slots=True)
class ConversationSummary:
    """Compressed older conversation context."""

    user_id: int
    summary: str
    updated_at: datetime
    covered_count: int = 0  # number of oldest messages already folded into the summary


@dataclass(frozen=True, slots=True)
class ContactStyleProfile:
    """Learned description of how the owner writes to a specific contact."""

    user_id: int
    profile: str
    updated_at: datetime
    covered_count: int = 0  # number of owner messages already folded into the profile
