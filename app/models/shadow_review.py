"""Owner-only blind A/B model comparison."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ShadowReview:
    id: int
    user_id: int
    candidate_id: str
    message_text: str
    reply_a: str | None
    reply_b: str | None
    mapping: str | None
    status: str
    winner: str | None
    created_at: datetime
    resolved_at: datetime | None
    error: str | None
