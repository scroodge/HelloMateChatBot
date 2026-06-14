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
