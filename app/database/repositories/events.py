"""Events repository — append-only usage log for admin stats."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import func, select

from app.database.schema import events
from app.database.util import now_iso

if TYPE_CHECKING:
    from app.database.db import Database


class EventRepository(Protocol):
    def record(self, user_id: int, event_type: str, meta: dict | None = None) -> None: ...
    def count_by_type(self, event_type: str, *, since: datetime | None = None) -> int: ...
    def counts_per_user(
        self, event_type: str, *, since: datetime | None = None
    ) -> dict[int, int]: ...
    def type_counts(self, *, since: datetime | None = None) -> dict[str, int]: ...


class EventRepositoryImpl:
    def __init__(self, database: Database) -> None:
        self._db = database

    def record(self, user_id: int, event_type: str, meta: dict | None = None) -> None:
        with self._db.engine.begin() as conn:
            conn.execute(
                events.insert().values(
                    user_id=user_id,
                    event_type=event_type,
                    meta=json.dumps(meta) if meta else None,
                    created_at=now_iso(),
                )
            )

    def count_by_type(self, event_type: str, *, since: datetime | None = None) -> int:
        stmt = select(func.count()).where(events.c.event_type == event_type)
        if since is not None:
            stmt = stmt.where(events.c.created_at >= since.isoformat())
        with self._db.engine.connect() as conn:
            return conn.execute(stmt).scalar_one()

    def counts_per_user(
        self, event_type: str, *, since: datetime | None = None
    ) -> dict[int, int]:
        stmt = (
            select(events.c.user_id, func.count().label("n"))
            .where(events.c.event_type == event_type)
            .group_by(events.c.user_id)
        )
        if since is not None:
            stmt = stmt.where(events.c.created_at >= since.isoformat())
        with self._db.engine.connect() as conn:
            rows = conn.execute(stmt).all()
        return {row.user_id: row.n for row in rows}

    def type_counts(self, *, since: datetime | None = None) -> dict[str, int]:
        stmt = select(events.c.event_type, func.count().label("n")).group_by(
            events.c.event_type
        )
        if since is not None:
            stmt = stmt.where(events.c.created_at >= since.isoformat())
        with self._db.engine.connect() as conn:
            rows = conn.execute(stmt).all()
        return {row.event_type: row.n for row in rows}
