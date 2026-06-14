"""Mood entry persistence repository."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from app.models.mood import MoodEntry

if TYPE_CHECKING:
    from app.database.sqlite import SQLiteDatabase


class MoodRepository(Protocol):
    """Persistence contract for mood entries."""

    def add_mood_entry(self, entry: MoodEntry) -> MoodEntry: ...

    def list_mood_entries(self, user_id: int, limit: int = 50) -> list[MoodEntry]: ...


class SQLiteMoodRepository:
    """SQLite implementation of MoodRepository."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def add_mood_entry(self, entry: MoodEntry) -> MoodEntry:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO mood_entries (user_id, mood, note, recorded_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    entry.user_id,
                    entry.mood,
                    entry.note,
                    entry.recorded_at.isoformat(),
                ),
            )
            entry_id = int(cursor.lastrowid)
        return MoodEntry(
            id=entry_id,
            user_id=entry.user_id,
            mood=entry.mood,
            note=entry.note,
            recorded_at=entry.recorded_at,
        )

    def list_mood_entries(self, user_id: int, limit: int = 50) -> list[MoodEntry]:
        rows = self._database.connection.execute(
            """
            SELECT id, user_id, mood, note, recorded_at
            FROM mood_entries
            WHERE user_id = ?
            ORDER BY recorded_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [
            MoodEntry(
                id=int(row["id"]),
                user_id=int(row["user_id"]),
                mood=int(row["mood"]),
                note=row["note"],
                recorded_at=datetime.fromisoformat(row["recorded_at"]),
            )
            for row in rows
        ]
