"""Versioned SQLite schema migrations."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_MIGRATION_PATTERN = re.compile(r"^(\d+)_.+\.sql$")


def _migration_files() -> list[tuple[int, Path]]:
    migrations: list[tuple[int, Path]] = []
    for path in MIGRATIONS_DIR.glob("*.sql"):
        match = _MIGRATION_PATTERN.match(path.name)
        if match is None:
            continue
        migrations.append((int(match.group(1)), path))
    return sorted(migrations, key=lambda item: item[0])


def _current_version(connection: sqlite3.Connection) -> int:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    row = connection.execute("SELECT MAX(version) AS version FROM schema_version").fetchone()
    if row is None or row["version"] is None:
        return 0
    return int(row["version"])


def run_migrations(connection: sqlite3.Connection) -> None:
    """Apply pending SQL migrations in numeric order."""

    current_version = _current_version(connection)
    for version, path in _migration_files():
        if version <= current_version:
            continue
        sql = path.read_text(encoding="utf-8")
        connection.executescript(sql)
        connection.execute(
            "INSERT INTO schema_version (version) VALUES (?)",
            (version,),
        )
        connection.commit()
