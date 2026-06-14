"""Tests for settings service."""

from __future__ import annotations

from app.models.settings import BotSetting, UserSettings
from app.services.settings_service import SettingsService


class InMemorySettingsRepository:
    def __init__(self) -> None:
        self.user_settings: dict[int, UserSettings] = {}
        self.bot_settings: dict[str, str] = {}

    def get_user_settings(self, user_id: int) -> UserSettings | None:
        return self.user_settings.get(user_id)

    def upsert_user_settings(self, settings: UserSettings) -> UserSettings:
        self.user_settings[settings.user_id] = settings
        return settings

    def list_user_settings(self) -> list[UserSettings]:
        return list(self.user_settings.values())

    def get_bot_setting(self, key: str) -> BotSetting | None:
        value = self.bot_settings.get(key)
        if value is None:
            return None
        return BotSetting(key=key, value=value)

    def set_bot_setting(self, key: str, value: str) -> BotSetting:
        self.bot_settings[key] = value
        return BotSetting(key=key, value=value)

    def list_bot_settings(self) -> list[BotSetting]:
        return [BotSetting(key=key, value=value) for key, value in self.bot_settings.items()]


def test_settings_service_returns_defaults() -> None:
    service = SettingsService(InMemorySettingsRepository(), "ru", 9)
    settings = service.get_user_settings(1)
    assert settings.language == "ru"
    assert settings.greeting_hour == 9
    assert settings.greeting_enabled is True


def test_settings_service_updates_language() -> None:
    service = SettingsService(InMemorySettingsRepository(), "ru", 9)
    updated = service.set_language(1, "en")
    assert updated.language == "en"
    assert service.get_language(1) == "en"


def test_global_greeting_toggle() -> None:
    repository = InMemorySettingsRepository()
    service = SettingsService(repository, "ru", 9)
    repository.bot_settings["greetings_enabled"] = "off"
    assert service.is_greeting_enabled(1) is False


def test_resolve_greeting_text_prefers_custom_text() -> None:
    service = SettingsService(InMemorySettingsRepository(), "ru", 9)
    service.set_greeting_text(42, "Привет, друг!")
    assert service.resolve_greeting_text(42, "Default") == "Привет, друг!"


def test_resolve_greeting_text_falls_back_to_default() -> None:
    service = SettingsService(InMemorySettingsRepository(), "ru", 9)
    assert service.resolve_greeting_text(42, "Default greeting") == "Default greeting"


def test_set_greeting_schedule_updates_interval_and_hour() -> None:
    service = SettingsService(InMemorySettingsRepository(), "ru", 9)
    updated = service.set_greeting_schedule(42, "weekly", hour=8, weekday=0)
    assert updated.greeting_interval == "weekly"
    assert updated.greeting_hour == 8
    assert updated.greeting_weekday == 0


def test_set_persona_prompt_stores_custom_text() -> None:
    service = SettingsService(InMemorySettingsRepository(), "ru", 9)
    updated = service.set_persona_prompt(42, "  You are a coach.  ")
    assert updated.persona_prompt == "You are a coach."
    assert service.persona_source(42) == "custom"
    assert service.resolve_persona_prompt(42, "ru") == "You are a coach."


def test_set_persona_prompt_clear_restores_fallback() -> None:
    service = SettingsService(InMemorySettingsRepository(), "ru", 9)
    service.set_persona_prompt(42, "Custom prompt")
    service.set_persona_prompt(42, None)
    assert service.get_user_settings(42).persona_prompt is None
    assert service.persona_source(42) == "builtin"


def test_resolve_persona_prompt_prefers_global_default() -> None:
    repository = InMemorySettingsRepository()
    service = SettingsService(repository, "ru", 9)
    repository.bot_settings["default_persona"] = "Global persona"
    assert service.resolve_persona_prompt(42, "ru") == "Global persona"
    assert service.persona_source(42) == "global"


def test_resolve_persona_prompt_user_override_beats_global() -> None:
    repository = InMemorySettingsRepository()
    service = SettingsService(repository, "ru", 9)
    repository.bot_settings["default_persona"] = "Global persona"
    service.set_persona_prompt(42, "User persona")
    assert service.resolve_persona_prompt(42, "ru") == "User persona"
    assert service.persona_source(42) == "custom"


def test_set_persona_prompt_rejects_empty_text() -> None:
    service = SettingsService(InMemorySettingsRepository(), "ru", 9)
    try:
        service.set_persona_prompt(42, "   ")
    except ValueError as error:
        assert "empty" in str(error)
    else:
        raise AssertionError("Expected ValueError for empty persona")


def test_set_persona_prompt_rejects_too_long_text() -> None:
    from app.services.settings_service import PERSONA_PROMPT_MAX_LENGTH

    service = SettingsService(InMemorySettingsRepository(), "ru", 9)
    try:
        service.set_persona_prompt(42, "x" * (PERSONA_PROMPT_MAX_LENGTH + 1))
    except ValueError as error:
        assert "at most" in str(error)
    else:
        raise AssertionError("Expected ValueError for long persona")

