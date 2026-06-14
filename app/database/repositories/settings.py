"""User and bot settings persistence repository."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sqlalchemy import select

from app.database.schema import bot_settings, user_settings
from app.database.util import now_iso, upsert
from app.models.settings import BotSetting, UserSettings

if TYPE_CHECKING:
    from app.database.db import Database


class SettingsRepository(Protocol):
    """Persistence contract for per-user and global bot settings."""

    def get_user_settings(self, user_id: int) -> UserSettings | None: ...

    def upsert_user_settings(self, settings: UserSettings) -> UserSettings: ...

    def list_user_settings(self) -> list[UserSettings]: ...

    def get_bot_setting(self, key: str) -> BotSetting | None: ...

    def set_bot_setting(self, key: str, value: str) -> BotSetting: ...

    def list_bot_settings(self) -> list[BotSetting]: ...


def _row_to_settings(row) -> UserSettings:
    return UserSettings(
        user_id=int(row.user_id),
        language=row.language,
        greeting_enabled=bool(row.greeting_enabled),
        greeting_hour=int(row.greeting_hour),
        use_starters=bool(row.use_starters),
        greeting_text=row.greeting_text,
        greeting_interval=row.greeting_interval,
        greeting_weekday=int(row.greeting_weekday),
        greeting_day=int(row.greeting_day),
        persona_prompt=row.persona_prompt,
        persona_preset=row.persona_preset,
        persona_relationship=row.persona_relationship,
        persona_tone=row.persona_tone,
        persona_topics=row.persona_topics,
        persona_boundaries=row.persona_boundaries,
        business_reply_mode=getattr(row, "business_reply_mode", None),
        openness=getattr(row, "openness", None),
        style_learning_enabled=bool(getattr(row, "style_learning_enabled", False)),
    )


class SettingsRepositoryImpl:
    """SQLAlchemy implementation of SettingsRepository."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def get_user_settings(self, user_id: int) -> UserSettings | None:
        with self._db.engine.connect() as connection:
            row = connection.execute(
                select(user_settings).where(user_settings.c.user_id == user_id)
            ).first()
        return _row_to_settings(row) if row is not None else None

    def upsert_user_settings(self, settings: UserSettings) -> UserSettings:
        values = {
            "user_id": settings.user_id,
            "language": settings.language,
            "greeting_enabled": settings.greeting_enabled,
            "greeting_hour": settings.greeting_hour,
            "use_starters": settings.use_starters,
            "greeting_text": settings.greeting_text,
            "greeting_interval": settings.greeting_interval,
            "greeting_weekday": settings.greeting_weekday,
            "greeting_day": settings.greeting_day,
            "persona_prompt": settings.persona_prompt,
            "persona_preset": settings.persona_preset,
            "persona_relationship": settings.persona_relationship,
            "persona_tone": settings.persona_tone,
            "persona_topics": settings.persona_topics,
            "persona_boundaries": settings.persona_boundaries,
            "business_reply_mode": settings.business_reply_mode,
            "openness": settings.openness,
            "style_learning_enabled": settings.style_learning_enabled,
            "updated_at": now_iso(),
        }
        with self._db.engine.begin() as connection:
            upsert(
                connection,
                user_settings,
                values,
                index_elements=["user_id"],
                update_columns=[key for key in values if key != "user_id"],
            )
        return settings

    def list_user_settings(self) -> list[UserSettings]:
        with self._db.engine.connect() as connection:
            rows = connection.execute(select(user_settings).order_by(user_settings.c.user_id)).all()
        return [_row_to_settings(row) for row in rows]

    def get_bot_setting(self, key: str) -> BotSetting | None:
        with self._db.engine.connect() as connection:
            row = connection.execute(select(bot_settings).where(bot_settings.c.key == key)).first()
        if row is None:
            return None
        return BotSetting(key=row.key, value=row.value)

    def set_bot_setting(self, key: str, value: str) -> BotSetting:
        with self._db.engine.begin() as connection:
            upsert(
                connection,
                bot_settings,
                {"key": key, "value": value, "updated_at": now_iso()},
                index_elements=["key"],
                update_columns=["value", "updated_at"],
            )
        return BotSetting(key=key, value=value)

    def list_bot_settings(self) -> list[BotSetting]:
        with self._db.engine.connect() as connection:
            rows = connection.execute(select(bot_settings).order_by(bot_settings.c.key)).all()
        return [BotSetting(key=row.key, value=row.value) for row in rows]
