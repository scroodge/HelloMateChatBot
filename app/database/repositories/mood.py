"""Mood entry persistence repository."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import insert, select

from app.database.schema import mood_entries
from app.models.mood import MoodEntry

if TYPE_CHECKING:
    from app.database.db import Database


class MoodRepository(Protocol):
    """Persistence contract for mood entries."""

    def add_mood_entry(self, entry: MoodEntry) -> MoodEntry: ...

    def list_mood_entries(self, user_id: int, limit: int = 50) -> list[MoodEntry]: ...


class MoodRepositoryImpl:
    """SQLAlchemy implementation of MoodRepository."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def add_mood_entry(self, entry: MoodEntry) -> MoodEntry:
        with self._db.engine.begin() as connection:
            result = connection.execute(
                insert(mood_entries).values(
                    user_id=entry.user_id,
                    mood=entry.mood,
                    note=entry.note,
                    recorded_at=entry.recorded_at.isoformat(),
                )
            )
            entry_id = int(result.inserted_primary_key[0])
        return MoodEntry(
            id=entry_id,
            user_id=entry.user_id,
            mood=entry.mood,
            note=entry.note,
            recorded_at=entry.recorded_at,
        )

    def list_mood_entries(self, user_id: int, limit: int = 50) -> list[MoodEntry]:
        with self._db.engine.connect() as connection:
            rows = connection.execute(
                select(mood_entries)
                .where(mood_entries.c.user_id == user_id)
                .order_by(mood_entries.c.recorded_at.desc())
                .limit(limit)
            ).all()
        return [
            MoodEntry(
                id=int(row.id),
                user_id=int(row.user_id),
                mood=int(row.mood),
                note=row.note,
                recorded_at=datetime.fromisoformat(row.recorded_at),
            )
            for row in rows
        ]
