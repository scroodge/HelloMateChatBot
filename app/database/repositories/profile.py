"""User profile persistence repository."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from app.models.profile import UserProfile

if TYPE_CHECKING:
    from app.database.sqlite import SQLiteDatabase


class ProfileRepository(Protocol):
    """Persistence contract for user profiles."""

    def get_profile(self, user_id: int) -> UserProfile | None: ...

    def upsert_profile(self, profile: UserProfile) -> UserProfile: ...

    def list_profiles(self) -> list[UserProfile]: ...


class SQLiteProfileRepository:
    """SQLite implementation of ProfileRepository."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def get_profile(self, user_id: int) -> UserProfile | None:
        row = self._database.connection.execute(
            """
            SELECT user_id, display_name, timezone_override, created_at, last_seen_at
            FROM user_profiles
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return UserProfile(
            user_id=int(row["user_id"]),
            display_name=row["display_name"],
            timezone_override=row["timezone_override"],
            created_at=datetime.fromisoformat(row["created_at"]),
            last_seen_at=datetime.fromisoformat(row["last_seen_at"]),
        )

    def upsert_profile(self, profile: UserProfile) -> UserProfile:
        with self._database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO user_profiles (
                    user_id, display_name, timezone_override, created_at, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    timezone_override = excluded.timezone_override,
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    profile.user_id,
                    profile.display_name,
                    profile.timezone_override,
                    profile.created_at.isoformat(),
                    profile.last_seen_at.isoformat(),
                ),
            )
        return profile

    def list_profiles(self) -> list[UserProfile]:
        rows = self._database.connection.execute(
            """
            SELECT user_id, display_name, timezone_override, created_at, last_seen_at
            FROM user_profiles
            ORDER BY user_id
            """
        ).fetchall()
        return [
            UserProfile(
                user_id=int(row["user_id"]),
                display_name=row["display_name"],
                timezone_override=row["timezone_override"],
                created_at=datetime.fromisoformat(row["created_at"]),
                last_seen_at=datetime.fromisoformat(row["last_seen_at"]),
            )
            for row in rows
        ]
