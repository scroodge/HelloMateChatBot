"""User profile persistence repository."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import select

from app.database.schema import user_profiles
from app.database.util import upsert
from app.models.profile import UserProfile

if TYPE_CHECKING:
    from app.database.db import Database


class ProfileRepository(Protocol):
    """Persistence contract for user profiles."""

    def get_profile(self, user_id: int) -> UserProfile | None: ...

    def upsert_profile(self, profile: UserProfile) -> UserProfile: ...

    def list_profiles(self) -> list[UserProfile]: ...


def _row_to_profile(row) -> UserProfile:
    return UserProfile(
        user_id=int(row.user_id),
        display_name=row.display_name,
        timezone_override=row.timezone_override,
        created_at=datetime.fromisoformat(row.created_at),
        last_seen_at=datetime.fromisoformat(row.last_seen_at),
    )


class ProfileRepositoryImpl:
    """SQLAlchemy implementation of ProfileRepository."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def get_profile(self, user_id: int) -> UserProfile | None:
        with self._db.engine.connect() as connection:
            row = connection.execute(
                select(user_profiles).where(user_profiles.c.user_id == user_id)
            ).first()
        return _row_to_profile(row) if row is not None else None

    def upsert_profile(self, profile: UserProfile) -> UserProfile:
        with self._db.engine.begin() as connection:
            upsert(
                connection,
                user_profiles,
                {
                    "user_id": profile.user_id,
                    "display_name": profile.display_name,
                    "timezone_override": profile.timezone_override,
                    "created_at": profile.created_at.isoformat(),
                    "last_seen_at": profile.last_seen_at.isoformat(),
                },
                index_elements=["user_id"],
                update_columns=["display_name", "timezone_override", "last_seen_at"],
            )
        return profile

    def list_profiles(self) -> list[UserProfile]:
        with self._db.engine.connect() as connection:
            rows = connection.execute(select(user_profiles).order_by(user_profiles.c.user_id)).all()
        return [_row_to_profile(row) for row in rows]
