"""User and bot settings persistence repository."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from app.models.settings import BotSetting, UserSettings

if TYPE_CHECKING:
    from app.database.sqlite import SQLiteDatabase


class SettingsRepository(Protocol):
    """Persistence contract for per-user and global bot settings."""

    def get_user_settings(self, user_id: int) -> UserSettings | None: ...

    def upsert_user_settings(self, settings: UserSettings) -> UserSettings: ...

    def list_user_settings(self) -> list[UserSettings]: ...

    def get_bot_setting(self, key: str) -> BotSetting | None: ...

    def set_bot_setting(self, key: str, value: str) -> BotSetting: ...

    def list_bot_settings(self) -> list[BotSetting]: ...


class SQLiteSettingsRepository:
    """SQLite implementation of SettingsRepository."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def get_user_settings(self, user_id: int) -> UserSettings | None:
        row = self._database.connection.execute(
            """
            SELECT user_id, language, greeting_enabled, greeting_hour, use_starters
            FROM user_settings
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return UserSettings(
            user_id=int(row["user_id"]),
            language=row["language"],
            greeting_enabled=bool(row["greeting_enabled"]),
            greeting_hour=int(row["greeting_hour"]),
            use_starters=bool(row["use_starters"]),
        )

    def upsert_user_settings(self, settings: UserSettings) -> UserSettings:
        with self._database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO user_settings (
                    user_id, language, greeting_enabled, greeting_hour, use_starters, updated_at
                )
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    language = excluded.language,
                    greeting_enabled = excluded.greeting_enabled,
                    greeting_hour = excluded.greeting_hour,
                    use_starters = excluded.use_starters,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    settings.user_id,
                    settings.language,
                    int(settings.greeting_enabled),
                    settings.greeting_hour,
                    int(settings.use_starters),
                ),
            )
        return settings

    def list_user_settings(self) -> list[UserSettings]:
        rows = self._database.connection.execute(
            """
            SELECT user_id, language, greeting_enabled, greeting_hour, use_starters
            FROM user_settings
            ORDER BY user_id
            """
        ).fetchall()
        return [
            UserSettings(
                user_id=int(row["user_id"]),
                language=row["language"],
                greeting_enabled=bool(row["greeting_enabled"]),
                greeting_hour=int(row["greeting_hour"]),
                use_starters=bool(row["use_starters"]),
            )
            for row in rows
        ]

    def get_bot_setting(self, key: str) -> BotSetting | None:
        row = self._database.connection.execute(
            "SELECT key, value FROM bot_settings WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        return BotSetting(key=row["key"], value=row["value"])

    def set_bot_setting(self, key: str, value: str) -> BotSetting:
        with self._database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO bot_settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, value),
            )
        return BotSetting(key=key, value=value)

    def list_bot_settings(self) -> list[BotSetting]:
        rows = self._database.connection.execute(
            "SELECT key, value FROM bot_settings ORDER BY key"
        ).fetchall()
        return [BotSetting(key=row["key"], value=row["value"]) for row in rows]
