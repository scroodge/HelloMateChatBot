"""Repository for owner personal-assistant profiles."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, insert, select, update

from app.database.schema import assistant_profiles
from app.models.assistant import AssistantProfile

if TYPE_CHECKING:
    from app.database.db import Database


class AssistantProfilesRepository:
    def list_profiles(self, owner_id: int) -> list[AssistantProfile]:
        raise NotImplementedError

    def get_by_name(self, owner_id: int, name: str) -> AssistantProfile | None:
        raise NotImplementedError

    def get_by_id(self, profile_id: int) -> AssistantProfile | None:
        raise NotImplementedError

    def upsert(self, owner_id: int, name: str, persona: str) -> AssistantProfile:
        raise NotImplementedError

    def delete(self, owner_id: int, name: str) -> None:
        raise NotImplementedError


def _row_to_profile(row) -> AssistantProfile:
    return AssistantProfile(
        id=int(row.id),
        owner_id=int(row.owner_id),
        name=row.name,
        persona=row.persona,
        created_at=datetime.fromisoformat(row.created_at),
    )


class AssistantProfilesRepositoryImpl(AssistantProfilesRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    def list_profiles(self, owner_id: int) -> list[AssistantProfile]:
        with self._db.engine.connect() as conn:
            rows = conn.execute(
                select(assistant_profiles)
                .where(assistant_profiles.c.owner_id == owner_id)
                .order_by(assistant_profiles.c.id.asc())
            ).fetchall()
        return [_row_to_profile(r) for r in rows]

    def get_by_name(self, owner_id: int, name: str) -> AssistantProfile | None:
        with self._db.engine.connect() as conn:
            row = conn.execute(
                select(assistant_profiles).where(
                    assistant_profiles.c.owner_id == owner_id,
                    assistant_profiles.c.name == name,
                )
            ).fetchone()
        return _row_to_profile(row) if row else None

    def get_by_id(self, profile_id: int) -> AssistantProfile | None:
        with self._db.engine.connect() as conn:
            row = conn.execute(
                select(assistant_profiles).where(assistant_profiles.c.id == profile_id)
            ).fetchone()
        return _row_to_profile(row) if row else None

    def upsert(self, owner_id: int, name: str, persona: str) -> AssistantProfile:
        now = datetime.now().astimezone().isoformat()
        with self._db.engine.begin() as conn:
            existing = conn.execute(
                select(assistant_profiles.c.id).where(
                    assistant_profiles.c.owner_id == owner_id,
                    assistant_profiles.c.name == name,
                )
            ).fetchone()
            if existing is None:
                result = conn.execute(
                    insert(assistant_profiles).values(
                        owner_id=owner_id, name=name, persona=persona, created_at=now
                    )
                )
                profile_id = int(result.inserted_primary_key[0])
                created_at = now
            else:
                profile_id = int(existing.id)
                conn.execute(
                    update(assistant_profiles)
                    .where(assistant_profiles.c.id == profile_id)
                    .values(persona=persona)
                )
                created_row = conn.execute(
                    select(assistant_profiles.c.created_at).where(
                        assistant_profiles.c.id == profile_id
                    )
                ).fetchone()
                created_at = created_row.created_at
        return AssistantProfile(
            id=profile_id,
            owner_id=owner_id,
            name=name,
            persona=persona,
            created_at=datetime.fromisoformat(created_at),
        )

    def delete(self, owner_id: int, name: str) -> None:
        with self._db.engine.begin() as conn:
            conn.execute(
                delete(assistant_profiles).where(
                    assistant_profiles.c.owner_id == owner_id,
                    assistant_profiles.c.name == name,
                )
            )
