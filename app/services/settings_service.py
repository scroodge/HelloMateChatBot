"""User and bot settings business logic."""

from __future__ import annotations

from app.database.repositories.settings import SettingsRepository
from app.i18n import supported_languages
from app.models.settings import UserSettings


class SettingsService:
    """Manage per-user and global bot settings."""

    def __init__(
        self,
        repository: SettingsRepository,
        default_language: str,
        default_greeting_hour: int,
    ) -> None:
        self.repository = repository
        self.default_language = default_language
        self.default_greeting_hour = default_greeting_hour

    def get_user_settings(self, user_id: int) -> UserSettings:
        """Return stored settings or defaults for a user."""

        settings = self.repository.get_user_settings(user_id)
        if settings is not None:
            return settings
        return UserSettings(
            user_id=user_id,
            language=self.default_language,
            greeting_hour=self.default_greeting_hour,
        )

    def save_user_settings(self, settings: UserSettings) -> UserSettings:
        """Persist user settings."""

        if settings.language not in supported_languages():
            raise ValueError(f"Unsupported language: {settings.language}")
        if not 0 <= settings.greeting_hour <= 23:
            raise ValueError("greeting_hour must be between 0 and 23")
        return self.repository.upsert_user_settings(settings)

    def get_language(self, user_id: int) -> str:
        """Return the effective language for a user."""

        return self.get_user_settings(user_id).language

    def set_language(self, user_id: int, language: str) -> UserSettings:
        """Update a user's language."""

        current = self.get_user_settings(user_id)
        updated = UserSettings(
            user_id=current.user_id,
            language=language,
            greeting_enabled=current.greeting_enabled,
            greeting_hour=current.greeting_hour,
            use_starters=current.use_starters,
        )
        return self.save_user_settings(updated)

    def set_greeting_enabled(self, user_id: int, enabled: bool) -> UserSettings:
        """Enable or disable greetings for a user."""

        current = self.get_user_settings(user_id)
        updated = UserSettings(
            user_id=current.user_id,
            language=current.language,
            greeting_enabled=enabled,
            greeting_hour=current.greeting_hour,
            use_starters=current.use_starters,
        )
        return self.save_user_settings(updated)

    def set_greeting_hour(self, user_id: int, hour: int) -> UserSettings:
        """Set the proactive greeting hour for a user."""

        current = self.get_user_settings(user_id)
        updated = UserSettings(
            user_id=current.user_id,
            language=current.language,
            greeting_enabled=current.greeting_enabled,
            greeting_hour=hour,
            use_starters=current.use_starters,
        )
        return self.save_user_settings(updated)

    def set_use_starters(self, user_id: int, enabled: bool) -> UserSettings:
        """Enable or disable conversation starters for a user."""

        current = self.get_user_settings(user_id)
        updated = UserSettings(
            user_id=current.user_id,
            language=current.language,
            greeting_enabled=current.greeting_enabled,
            greeting_hour=current.greeting_hour,
            use_starters=enabled,
        )
        return self.save_user_settings(updated)

    def get_bot_setting(self, key: str, default: str = "") -> str:
        """Return a global bot setting value."""

        setting = self.repository.get_bot_setting(key)
        if setting is None:
            return default
        return setting.value

    def set_bot_setting(self, key: str, value: str) -> str:
        """Persist a global bot setting."""

        return self.repository.set_bot_setting(key, value).value

    def list_bot_settings(self) -> dict[str, str]:
        """Return all global bot settings."""

        return {item.key: item.value for item in self.repository.list_bot_settings()}

    def list_all_user_settings(self) -> list[UserSettings]:
        """Return all stored user settings."""

        return self.repository.list_user_settings()

    def is_greeting_enabled(self, user_id: int) -> bool:
        """Return whether greetings are enabled for a user."""

        global_enabled = self.get_bot_setting("greetings_enabled", "on").lower() != "off"
        return global_enabled and self.get_user_settings(user_id).greeting_enabled
