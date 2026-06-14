"""Greeting persistence repository."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import select

from app.database.schema import user_greetings
from app.database.util import now_iso, upsert

if TYPE_CHECKING:
    from app.database.db import Database


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


class GreetingRepositoryImpl:
    """SQLAlchemy implementation of GreetingRepository."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def get_last_greeting_date(self, user_id: int) -> date | None:
        with self._db.engine.connect() as connection:
            row = connection.execute(
                select(user_greetings.c.last_greeting_date).where(
                    user_greetings.c.user_id == user_id
                )
            ).first()
        if row is None:
            return None
        return date.fromisoformat(row.last_greeting_date)

    def set_last_greeting_date(self, user_id: int, greeting_date: date) -> None:
        with self._db.engine.begin() as connection:
            upsert(
                connection,
                user_greetings,
                {
                    "user_id": user_id,
                    "last_greeting_date": greeting_date.isoformat(),
                    "updated_at": now_iso(),
                },
                index_elements=["user_id"],
                update_columns=["last_greeting_date", "updated_at"],
            )

    def list_user_ids(self) -> list[int]:
        with self._db.engine.connect() as connection:
            rows = connection.execute(
                select(user_greetings.c.user_id).order_by(user_greetings.c.user_id)
            ).all()
        return [int(row.user_id) for row in rows]
