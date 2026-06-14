"""Repository for per-contact durable facts."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from app.database.schema import contact_facts, contact_facts_meta
from app.models.facts import ContactFact, ContactFactsMeta

if TYPE_CHECKING:
    from app.database.db import Database


class ContactFactsRepository:
    def get_facts(self, user_id: int) -> list[ContactFact]:
        raise NotImplementedError

    def set_fact(self, user_id: int, key: str, value: str) -> None:
        raise NotImplementedError

    def delete_fact(self, user_id: int, key: str) -> None:
        raise NotImplementedError

    def clear_facts(self, user_id: int) -> None:
        raise NotImplementedError

    def get_meta(self, user_id: int) -> ContactFactsMeta | None:
        raise NotImplementedError

    def set_meta(self, user_id: int, last_message_count: int) -> None:
        raise NotImplementedError


class ContactFactsRepositoryImpl(ContactFactsRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    def get_facts(self, user_id: int) -> list[ContactFact]:
        with self._db.engine.connect() as conn:
            rows = conn.execute(
                select(contact_facts).where(contact_facts.c.user_id == user_id)
            ).fetchall()
        return [
            ContactFact(
                user_id=row.user_id,
                key=row.key,
                value=row.value,
                updated_at=datetime.fromisoformat(row.updated_at),
            )
            for row in rows
        ]

    def set_fact(self, user_id: int, key: str, value: str) -> None:
        now = datetime.now().astimezone().isoformat()
        with self._db.engine.begin() as conn:
            existing = conn.execute(
                select(contact_facts).where(
                    contact_facts.c.user_id == user_id,
                    contact_facts.c.key == key,
                )
            ).fetchone()
            if existing is None:
                conn.execute(
                    contact_facts.insert().values(
                        user_id=user_id, key=key, value=value, updated_at=now
                    )
                )
            else:
                conn.execute(
                    contact_facts.update()
                    .where(
                        contact_facts.c.user_id == user_id,
                        contact_facts.c.key == key,
                    )
                    .values(value=value, updated_at=now)
                )

    def delete_fact(self, user_id: int, key: str) -> None:
        with self._db.engine.begin() as conn:
            conn.execute(
                delete(contact_facts).where(
                    contact_facts.c.user_id == user_id,
                    contact_facts.c.key == key,
                )
            )

    def clear_facts(self, user_id: int) -> None:
        with self._db.engine.begin() as conn:
            conn.execute(
                delete(contact_facts).where(contact_facts.c.user_id == user_id)
            )

    def get_meta(self, user_id: int) -> ContactFactsMeta | None:
        with self._db.engine.connect() as conn:
            row = conn.execute(
                select(contact_facts_meta).where(
                    contact_facts_meta.c.user_id == user_id
                )
            ).fetchone()
        if row is None:
            return None
        return ContactFactsMeta(
            user_id=row.user_id,
            last_message_count=row.last_message_count,
            updated_at=datetime.fromisoformat(row.updated_at),
        )

    def set_meta(self, user_id: int, last_message_count: int) -> None:
        now = datetime.now().astimezone().isoformat()
        with self._db.engine.begin() as conn:
            existing = conn.execute(
                select(contact_facts_meta).where(
                    contact_facts_meta.c.user_id == user_id
                )
            ).fetchone()
            if existing is None:
                conn.execute(
                    contact_facts_meta.insert().values(
                        user_id=user_id,
                        last_message_count=last_message_count,
                        updated_at=now,
                    )
                )
            else:
                conn.execute(
                    contact_facts_meta.update()
                    .where(contact_facts_meta.c.user_id == user_id)
                    .values(last_message_count=last_message_count, updated_at=now)
                )
