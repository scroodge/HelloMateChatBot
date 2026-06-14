"""User and bot settings models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UserSettings:
    """Per-user bot behavior settings."""

    user_id: int
    language: str = "ru"
    greeting_enabled: bool = True
    greeting_hour: int = 9
    use_starters: bool = False


@dataclass(frozen=True, slots=True)
class BotSetting:
    """Global bot configuration entry."""

    key: str
    value: str
