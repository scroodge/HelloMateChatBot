"""Greeting persistence repository."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.database.sqlite import SQLiteDatabase


class GreetingRepository(Protocol):
    """Persistence contract used by GreetingService."""

    def get_last_greeting_date(self, user_id: int) -> date | None:
        """Return the last greeting date for a user, if present."""
        ...

    def set_last_greeting_date(self, user_id: int, greeting_date: date) -> None:
        """Persist the last greeting date for a user."""
        ...

    def list_user_ids(self) -> list[int]:
        """Return all user IDs with greeting records."""
        ...


class SQLiteGreetingRepository:
    """SQLite implementation of GreetingRepository."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def get_last_greeting_date(self, user_id: int) -> date | None:
        row = self._database.connection.execute(
            "SELECT last_greeting_date FROM user_greetings WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return date.fromisoformat(row["last_greeting_date"])

    def set_last_greeting_date(self, user_id: int, greeting_date: date) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO user_greetings (user_id, last_greeting_date, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    last_greeting_date = excluded.last_greeting_date,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, greeting_date.isoformat()),
            )

    def list_user_ids(self) -> list[int]:
        rows = self._database.connection.execute(
            "SELECT user_id FROM user_greetings ORDER BY user_id"
        ).fetchall()
        return [int(row["user_id"]) for row in rows]
