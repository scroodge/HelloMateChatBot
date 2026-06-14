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


@dataclass(frozen=True, slots=True)
class ConversationSummary:
    """Compressed older conversation context."""

    user_id: int
    summary: str
    updated_at: datetime
    covered_count: int = 0  # number of oldest messages already folded into the summary
