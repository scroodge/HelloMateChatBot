"""Tests for database migrations."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.database.migrations import run_migrations


def test_run_migrations_on_empty_database(tmp_path: Path) -> None:
    database_path = tmp_path / "test.db"
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    run_migrations(connection)

    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    connection.close()

    assert "schema_version" in tables
    assert "user_greetings" in tables
    assert "user_settings" in tables
    assert "user_profiles" in tables
    assert "documents" in tables
