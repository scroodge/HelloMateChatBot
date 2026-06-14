"""User and bot settings business logic."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from app.database.repositories.settings import SettingsRepository
from app.i18n import supported_languages
from app.models.settings import UserSettings
from app.services.greeting_schedule import GREETING_INTERVALS

if TYPE_CHECKING:
    from app.services.conversation_starter_service import ConversationStarterService


PERSONA_PROMPT_MAX_LENGTH = 4000
DEFAULT_PERSONA_BOT_SETTING = "default_persona"


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
        if settings.greeting_interval not in GREETING_INTERVALS:
            raise ValueError(f"Unsupported greeting interval: {settings.greeting_interval}")
        if not 0 <= settings.greeting_weekday <= 6:
            raise ValueError("greeting_weekday must be between 0 and 6")
        if not 1 <= settings.greeting_day <= 31:
            raise ValueError("greeting_day must be between 1 and 31")
        return self.repository.upsert_user_settings(settings)

    def get_language(self, user_id: int) -> str:
        """Return the effective language for a user."""

        return self.get_user_settings(user_id).language

    def _with_current(self, user_id: int) -> UserSettings:
        return self.get_user_settings(user_id)

    def set_language(self, user_id: int, language: str) -> UserSettings:
        """Update a user's language."""

        return self.save_user_settings(replace(self._with_current(user_id), language=language))

    def set_greeting_enabled(self, user_id: int, enabled: bool) -> UserSettings:
        """Enable or disable greetings for a user."""

        return self.save_user_settings(
            replace(self._with_current(user_id), greeting_enabled=enabled)
        )

    def set_greeting_hour(self, user_id: int, hour: int) -> UserSettings:
        """Set the proactive greeting hour for a user."""

        return self.save_user_settings(replace(self._with_current(user_id), greeting_hour=hour))

    def set_use_starters(self, user_id: int, enabled: bool) -> UserSettings:
        """Enable or disable conversation starters for a user."""

        return self.save_user_settings(replace(self._with_current(user_id), use_starters=enabled))

    def set_greeting_text(self, user_id: int, text: str | None) -> UserSettings:
        """Set or clear a user's custom greeting text."""

        return self.save_user_settings(replace(self._with_current(user_id), greeting_text=text))

    def set_persona_prompt(self, user_id: int, text: str | None) -> UserSettings:
        """Set or clear a user's custom AI persona prompt."""

        normalized = text.strip() if text is not None else None
        self._validate_persona_prompt(normalized)
        return self.save_user_settings(
            replace(self._with_current(user_id), persona_prompt=normalized)
        )

    def resolve_persona_prompt(
        self,
        user_id: int,
        language: str,
        display_name: str | None = None,
    ) -> str:
        """Return the effective system prompt for AI replies."""

        settings = self.get_user_settings(user_id)
        if settings.persona_prompt:
            return settings.persona_prompt

        global_persona = self.get_bot_setting(DEFAULT_PERSONA_BOT_SETTING, "").strip()
        if global_persona:
            return global_persona

        from app.services.reply_service import build_persona_prompt

        return build_persona_prompt(language, display_name)

    def persona_source(self, user_id: int) -> str:
        """Return persona origin: custom, global, or builtin."""

        settings = self.get_user_settings(user_id)
        if settings.persona_prompt:
            return "custom"
        if self.get_bot_setting(DEFAULT_PERSONA_BOT_SETTING, "").strip():
            return "global"
        return "builtin"

    def _validate_persona_prompt(self, text: str | None) -> None:
        if text is None:
            return
        if not text:
            raise ValueError("persona_prompt cannot be empty")
        if len(text) > PERSONA_PROMPT_MAX_LENGTH:
            raise ValueError(
                f"persona_prompt must be at most {PERSONA_PROMPT_MAX_LENGTH} characters"
            )

    def set_greeting_schedule(
        self,
        user_id: int,
        interval: str,
        *,
        hour: int | None = None,
        weekday: int | None = None,
        day_of_month: int | None = None,
    ) -> UserSettings:
        """Set greeting frequency and optional time/day details."""

        current = self._with_current(user_id)
        updated = replace(
            current,
            greeting_interval=interval,
            greeting_hour=hour if hour is not None else current.greeting_hour,
            greeting_weekday=weekday if weekday is not None else current.greeting_weekday,
            greeting_day=day_of_month if day_of_month is not None else current.greeting_day,
        )
        return self.save_user_settings(updated)

    def resolve_greeting_text(
        self,
        user_id: int,
        default_text: str,
        starter_service: ConversationStarterService | None = None,
    ) -> str:
        """Return the greeting text for a user."""

        settings = self.get_user_settings(user_id)
        if settings.greeting_text:
            return settings.greeting_text
        if settings.use_starters and starter_service is not None:
            starter = starter_service.pick()
            if starter:
                return starter
        return default_text

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
