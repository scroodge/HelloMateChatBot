"""SQLite persistence for user greeting state."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from types import TracebackType


class SQLiteDatabase:
    """Small SQLite adapter for storing the last greeting date per user."""

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)
        self._connection: sqlite3.Connection | None = None

    def connect(self) -> None:
        """Open the database connection and initialize the schema."""

        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        self._connection = connection
        self.initialize_schema()

    def close(self) -> None:
        """Close the database connection."""

        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self) -> "SQLiteDatabase":
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def connection(self) -> sqlite3.Connection:
        """Return an active SQLite connection."""

        if self._connection is None:
            raise RuntimeError("Database is not connected. Call connect() first.")
        return self._connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Commit or roll back a short write transaction."""

        connection = self.connection
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def initialize_schema(self) -> None:
        """Create database tables if they do not already exist."""

        with self.transaction() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS user_greetings (
                    user_id INTEGER PRIMARY KEY,
                    last_greeting_date TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def get_last_greeting_date(self, user_id: int) -> date | None:
        """Return the last date a user received a daily greeting."""

        row = self.connection.execute(
            "SELECT last_greeting_date FROM user_greetings WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return date.fromisoformat(row["last_greeting_date"])

    def set_last_greeting_date(self, user_id: int, greeting_date: date) -> None:
        """Persist the last date a user received a daily greeting."""

        with self.transaction() as connection:
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

