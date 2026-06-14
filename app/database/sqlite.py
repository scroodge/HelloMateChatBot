"""SQLite persistence for HelloMate."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import TracebackType

from app.database.migrations import run_migrations
from app.database.repositories.documents import SQLiteDocumentRepository
from app.database.repositories.greeting import SQLiteGreetingRepository
from app.database.repositories.greeting_rules import SQLiteGreetingRulesRepository
from app.database.repositories.memory import SQLiteMemoryRepository
from app.database.repositories.mood import SQLiteMoodRepository
from app.database.repositories.profile import SQLiteProfileRepository
from app.database.repositories.settings import SQLiteSettingsRepository


class SQLiteDatabase:
    """SQLite connection manager with repository accessors.

    The bot runs Telegram handlers on the asyncio loop while the FastAPI Mini App
    runs in a separate thread. A single ``sqlite3.Connection`` cannot be shared
    across threads, so each thread gets its own connection. WAL mode allows
    concurrent readers with a single writer, and ``busy_timeout`` absorbs brief
    write contention between the bot and the API.
    """

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)
        self._local = threading.local()
        self._connections: list[sqlite3.Connection] = []
        self._lock = threading.Lock()
        self._migrated = False
        self.greetings = SQLiteGreetingRepository(self)
        self.greeting_rules = SQLiteGreetingRulesRepository(self)
        self.settings = SQLiteSettingsRepository(self)
        self.profiles = SQLiteProfileRepository(self)
        self.moods = SQLiteMoodRepository(self)
        self.memory = SQLiteMemoryRepository(self)
        self.documents = SQLiteDocumentRepository(self)

    def _new_connection(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        with self._lock:
            self._connections.append(connection)
        return connection

    def connect(self) -> None:
        """Open a connection for the current thread and run pending migrations."""

        connection = self.connection
        if not self._migrated:
            run_migrations(connection)
            self._migrated = True

    def close(self) -> None:
        """Close every connection opened across threads."""

        with self._lock:
            for connection in self._connections:
                connection.close()
            self._connections.clear()
        self._local = threading.local()
        self._migrated = False

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
        """Return the calling thread's SQLite connection, creating it on demand."""

        connection = getattr(self._local, "connection", None)
        if connection is None:
            connection = self._new_connection()
            self._local.connection = connection
        return connection

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
