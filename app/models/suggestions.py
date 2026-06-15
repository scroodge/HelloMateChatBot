"""Suggest-inbox models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Suggestion:
    """A drafted reply awaiting the owner's review in suggest mode."""

    user_id: int
    contact_message: str
    draft_text: str
    status: str
    created_at: datetime
    id: int | None = None
