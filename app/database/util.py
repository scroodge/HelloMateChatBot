"""Shared helpers for the SQLAlchemy Core repositories."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import Table
from sqlalchemy.engine import Connection


def now_iso() -> str:
    """Return the current time as an ISO-8601 string for ``updated_at`` columns."""

    return datetime.now().isoformat()


def upsert(
    connection: Connection,
    table: Table,
    values: Mapping[str, Any],
    *,
    index_elements: Iterable[str],
    update_columns: Iterable[str],
) -> None:
    """Run a dialect-aware INSERT ... ON CONFLICT DO UPDATE.

    SQLite and PostgreSQL both support ``on_conflict_do_update`` but expose it
    through dialect-specific ``insert`` constructs, so we pick the right one at
    runtime based on the active dialect.
    """

    dialect = connection.engine.dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as dialect_insert
    else:
        from sqlalchemy.dialects.sqlite import insert as dialect_insert

    statement = dialect_insert(table).values(**values)
    statement = statement.on_conflict_do_update(
        index_elements=list(index_elements),
        set_={column: statement.excluded[column] for column in update_columns},
    )
    connection.execute(statement)
