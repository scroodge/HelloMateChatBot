"""Repository for per-contact durable facts."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import delete, select

from app.database.schema import contact_fact_history, contact_facts, contact_facts_meta
from app.models.facts import ContactFact, ContactFactHistory, ContactFactsMeta

if TYPE_CHECKING:
    from app.database.db import Database


class ContactFactsRepository:
    def get_facts(self, user_id: int) -> list[ContactFact]:
        raise NotImplementedError

    def set_fact(
        self,
        user_id: int,
        key: str,
        value: str,
        *,
        source_message_id: int | None = None,
        confidence: float | None = None,
        owner_confirmed: bool = False,
    ) -> None:
        raise NotImplementedError

    def get_history(self, user_id: int, key: str) -> list[ContactFactHistory]:
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
        return [self._fact_from_row(row) for row in rows]

    def set_fact(
        self,
        user_id: int,
        key: str,
        value: str,
        *,
        source_message_id: int | None = None,
        confidence: float | None = None,
        owner_confirmed: bool = False,
    ) -> None:
        now = datetime.now().astimezone()
        now_text = now.isoformat()
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
                        user_id=user_id,
                        key=key,
                        value=value,
                        updated_at=now_text,
                        source_message_id=source_message_id,
                        confidence=confidence,
                        first_observed_at=now_text,
                        last_observed_at=now_text,
                        valid_from=now_text,
                        valid_until=None,
                        owner_confirmed=owner_confirmed,
                        version_id=self._version_id(user_id, key, now),
                    )
                )
            elif existing.value == value:
                conn.execute(
                    contact_facts.update()
                    .where(
                        contact_facts.c.user_id == user_id,
                        contact_facts.c.key == key,
                    )
                    .values(
                        updated_at=now_text,
                        last_observed_at=now_text,
                        confidence=self._higher_confidence(existing.confidence, confidence),
                        source_message_id=source_message_id or existing.source_message_id,
                        owner_confirmed=bool(existing.owner_confirmed) or owner_confirmed,
                    )
                )
            else:
                next_version_id = self._version_id(user_id, key, now)
                self._archive_row(
                    conn, existing, valid_until=now_text, superseded_by=next_version_id
                )
                conn.execute(
                    contact_facts.update()
                    .where(
                        contact_facts.c.user_id == user_id,
                        contact_facts.c.key == key,
                    )
                    .values(
                        value=value,
                        updated_at=now_text,
                        source_message_id=source_message_id,
                        confidence=confidence,
                        first_observed_at=now_text,
                        last_observed_at=now_text,
                        valid_from=now_text,
                        valid_until=None,
                        owner_confirmed=owner_confirmed,
                        version_id=next_version_id,
                    )
                )

    def get_history(self, user_id: int, key: str) -> list[ContactFactHistory]:
        with self._db.engine.connect() as conn:
            rows = conn.execute(
                select(contact_fact_history)
                .where(
                    contact_fact_history.c.user_id == user_id,
                    contact_fact_history.c.key == key,
                )
                .order_by(contact_fact_history.c.created_at.desc())
            ).fetchall()
        return [
            ContactFactHistory(
                id=int(row.id),
                user_id=int(row.user_id),
                key=row.key,
                value=row.value,
                source_message_id=row.source_message_id,
                confidence=row.confidence,
                first_observed_at=self._parse_datetime(row.first_observed_at),
                last_observed_at=self._parse_datetime(row.last_observed_at),
                valid_from=self._parse_datetime(row.valid_from),
                valid_until=self._parse_datetime(row.valid_until),
                owner_confirmed=bool(row.owner_confirmed),
                version_id=row.version_id,
                superseded_by=row.superseded_by,
            )
            for row in rows
        ]

    def delete_fact(self, user_id: int, key: str) -> None:
        with self._db.engine.begin() as conn:
            existing = conn.execute(
                select(contact_facts).where(
                    contact_facts.c.user_id == user_id,
                    contact_facts.c.key == key,
                )
            ).fetchone()
            if existing is not None:
                self._archive_row(
                    conn,
                    existing,
                    valid_until=datetime.now().astimezone().isoformat(),
                    superseded_by=None,
                )
            conn.execute(
                delete(contact_facts).where(
                    contact_facts.c.user_id == user_id,
                    contact_facts.c.key == key,
                )
            )

    def clear_facts(self, user_id: int) -> None:
        with self._db.engine.begin() as conn:
            conn.execute(delete(contact_facts).where(contact_facts.c.user_id == user_id))
            conn.execute(
                delete(contact_fact_history).where(contact_fact_history.c.user_id == user_id)
            )
            conn.execute(delete(contact_facts_meta).where(contact_facts_meta.c.user_id == user_id))

    def get_meta(self, user_id: int) -> ContactFactsMeta | None:
        with self._db.engine.connect() as conn:
            row = conn.execute(
                select(contact_facts_meta).where(contact_facts_meta.c.user_id == user_id)
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
                select(contact_facts_meta).where(contact_facts_meta.c.user_id == user_id)
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

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        return datetime.fromisoformat(value) if value else None

    def _fact_from_row(self, row: object) -> ContactFact:
        updated_at = datetime.fromisoformat(row.updated_at)
        return ContactFact(
            user_id=int(row.user_id),
            key=row.key,
            value=row.value,
            updated_at=updated_at,
            source_message_id=getattr(row, "source_message_id", None),
            confidence=getattr(row, "confidence", None),
            first_observed_at=self._parse_datetime(getattr(row, "first_observed_at", None))
            or updated_at,
            last_observed_at=self._parse_datetime(getattr(row, "last_observed_at", None))
            or updated_at,
            valid_from=self._parse_datetime(getattr(row, "valid_from", None)) or updated_at,
            valid_until=self._parse_datetime(getattr(row, "valid_until", None)),
            owner_confirmed=bool(getattr(row, "owner_confirmed", False)),
            version_id=getattr(row, "version_id", None),
        )

    @staticmethod
    def _higher_confidence(existing: float | None, incoming: float | None) -> float | None:
        if existing is None:
            return incoming
        if incoming is None:
            return existing
        return max(existing, incoming)

    @staticmethod
    def _version_id(user_id: int, key: str, observed_at: datetime) -> str:
        return f"fact:{user_id}:{key}:{observed_at.isoformat()}:{uuid4().hex[:12]}"

    @staticmethod
    def _archive_row(
        conn: object, row: object, *, valid_until: str, superseded_by: str | None
    ) -> None:
        conn.execute(
            contact_fact_history.insert().values(
                user_id=row.user_id,
                key=row.key,
                value=row.value,
                source_message_id=getattr(row, "source_message_id", None),
                confidence=getattr(row, "confidence", None),
                first_observed_at=getattr(row, "first_observed_at", None) or row.updated_at,
                last_observed_at=getattr(row, "last_observed_at", None) or row.updated_at,
                valid_from=getattr(row, "valid_from", None) or row.updated_at,
                valid_until=valid_until,
                owner_confirmed=bool(getattr(row, "owner_confirmed", False)),
                version_id=getattr(row, "version_id", None),
                superseded_by=superseded_by,
                created_at=valid_until,
            )
        )
