"""A reviewable pairing between a Suggest Inbox draft and an owner reply."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class OwnerReplyPair:
    id: int
    suggestion_id: int
    user_id: int
    owner_message_id: int
    owner_reply_text: str
    confidence: float
    status: str
    reason: str | None
    created_at: datetime
    resolved_at: datetime | None
