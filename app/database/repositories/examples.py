"""Repository for per-contact few-shot examples."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, insert, select

from app.database.schema import contact_examples
from app.models.examples import ContactExample

if TYPE_CHECKING:
    from app.database.db import Database


class ContactExamplesRepository:
    def list_examples(self, user_id: int) -> list[ContactExample]:
        raise NotImplementedError

    def add_example(
        self, user_id: int, contact_message: str, reply_text: str, kind: str = "positive"
    ) -> ContactExample:
        raise NotImplementedError

    def delete_example(self, user_id: int, example_id: int) -> None:
        raise NotImplementedError

    def clear_examples(self, user_id: int) -> None:
        raise NotImplementedError

    def count_examples(self, user_id: int) -> int:
        raise NotImplementedError

    def count_by_kind(self, user_id: int, kind: str) -> int:
        raise NotImplementedError

    def global_stats(self) -> tuple[int, int]:
        raise NotImplementedError


class ContactExamplesRepositoryImpl(ContactExamplesRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    def list_examples(self, user_id: int) -> list[ContactExample]:
        with self._db.engine.connect() as conn:
            rows = conn.execute(
                select(contact_examples)
                .where(contact_examples.c.user_id == user_id)
                .order_by(contact_examples.c.id.asc())
            ).fetchall()
        return [
            ContactExample(
                id=int(row.id),
                user_id=int(row.user_id),
                contact_message=row.contact_message,
                reply_text=row.reply_text,
                kind=row.kind if hasattr(row, "kind") else "positive",
                created_at=datetime.fromisoformat(row.created_at),
            )
            for row in rows
        ]

    def add_example(
        self, user_id: int, contact_message: str, reply_text: str, kind: str = "positive"
    ) -> ContactExample:
        now = datetime.now().astimezone()
        with self._db.engine.begin() as conn:
            result = conn.execute(
                insert(contact_examples).values(
                    user_id=user_id,
                    contact_message=contact_message,
                    reply_text=reply_text,
                    kind=kind,
                    created_at=now.isoformat(),
                )
            )
            example_id = int(result.inserted_primary_key[0])
        return ContactExample(
            id=example_id,
            user_id=user_id,
            contact_message=contact_message,
            reply_text=reply_text,
            kind=kind,
            created_at=now,
        )

    def delete_example(self, user_id: int, example_id: int) -> None:
        with self._db.engine.begin() as conn:
            conn.execute(
                delete(contact_examples).where(
                    contact_examples.c.user_id == user_id,
                    contact_examples.c.id == example_id,
                )
            )

    def clear_examples(self, user_id: int) -> None:
        with self._db.engine.begin() as conn:
            conn.execute(delete(contact_examples).where(contact_examples.c.user_id == user_id))

    def count_examples(self, user_id: int) -> int:
        with self._db.engine.connect() as conn:
            return int(
                conn.execute(
                    select(func.count())
                    .select_from(contact_examples)
                    .where(contact_examples.c.user_id == user_id)
                ).scalar_one()
            )

    def count_by_kind(self, user_id: int, kind: str) -> int:
        with self._db.engine.connect() as conn:
            return int(
                conn.execute(
                    select(func.count())
                    .select_from(contact_examples)
                    .where(
                        contact_examples.c.user_id == user_id,
                        contact_examples.c.kind == kind,
                    )
                ).scalar_one()
            )

    def global_stats(self) -> tuple[int, int]:
        """Return (total examples, number of distinct contacts with examples)."""
        with self._db.engine.connect() as conn:
            total = int(
                conn.execute(select(func.count()).select_from(contact_examples)).scalar_one()
            )
            contacts = int(
                conn.execute(
                    select(func.count(func.distinct(contact_examples.c.user_id)))
                ).scalar_one()
            )
        return total, contacts
