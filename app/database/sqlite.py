"""SQLite persistence for HelloMate."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import TracebackType

from app.database.migrations import run_migrations
from app.database.repositories.documents import SQLiteDocumentRepository
from app.database.repositories.greeting import SQLiteGreetingRepository
from app.database.repositories.memory import SQLiteMemoryRepository
from app.database.repositories.mood import SQLiteMoodRepository
from app.database.repositories.profile import SQLiteProfileRepository
from app.database.repositories.settings import SQLiteSettingsRepository


class SQLiteDatabase:
    """SQLite connection manager with repository accessors."""

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)
        self._connection: sqlite3.Connection | None = None
        self.greetings = SQLiteGreetingRepository(self)
        self.settings = SQLiteSettingsRepository(self)
        self.profiles = SQLiteProfileRepository(self)
        self.moods = SQLiteMoodRepository(self)
        self.memory = SQLiteMemoryRepository(self)
        self.documents = SQLiteDocumentRepository(self)

    def connect(self) -> None:
        """Open the database connection and run pending migrations."""

        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        self._connection = connection
        run_migrations(connection)

    def close(self) -> None:
        """Close the database connection."""

        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self) -> SQLiteDatabase:
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
