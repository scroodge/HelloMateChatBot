"""Mood tracking models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class MoodEntry:
    """A single mood check-in."""

    user_id: int
    mood: int
    recorded_at: datetime
    note: str | None = None
    id: int | None = None
