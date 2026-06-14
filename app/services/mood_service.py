"""Mood tracking business logic."""

from __future__ import annotations

from datetime import datetime

from app.database.repositories.mood import MoodRepository
from app.models.mood import MoodEntry


class MoodService:
    """Record and retrieve mood entries."""

    def __init__(self, repository: MoodRepository) -> None:
        self.repository = repository

    def record_mood(
        self,
        user_id: int,
        mood: int,
        note: str | None = None,
        now: datetime | None = None,
    ) -> MoodEntry:
        """Store a mood check-in."""

        if not 1 <= mood <= 5:
            raise ValueError("mood must be between 1 and 5")
        entry = MoodEntry(
            user_id=user_id,
            mood=mood,
            note=note,
            recorded_at=now or datetime.now().astimezone(),
        )
        return self.repository.add_mood_entry(entry)

    def recent_entries(self, user_id: int, limit: int = 7) -> list[MoodEntry]:
        """Return recent mood entries newest first."""

        return self.repository.list_mood_entries(user_id, limit=limit)

    def latest_mood(self, user_id: int) -> MoodEntry | None:
        """Return the most recent mood entry."""

        entries = self.repository.list_mood_entries(user_id, limit=1)
        if not entries:
            return None
        return entries[0]
