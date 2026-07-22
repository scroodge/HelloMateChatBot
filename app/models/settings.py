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
    greeting_text: str | None = None
    greeting_interval: str = "daily"
    greeting_weekday: int = 0
    greeting_day: int = 1
    persona_prompt: str | None = None
    # structured persona fields (slice 6A)
    persona_preset: str | None = None  # e.g. "friend", "family", "mentor"
    persona_relationship: str | None = None  # free-text e.g. "older brother"
    persona_tone: str | None = None  # e.g. "warm", "formal", "playful"
    persona_topics: str | None = None  # JSON list of allowed topics
    persona_boundaries: str | None = None  # JSON list of forbidden topics
    business_reply_mode: str | None = None  # "suggest" | "off" | None=inherit global
    openness: str | None = None  # "open" | "neutral" | "reserved" | None=inherit global
    style_learning_enabled: bool = False  # learn the owner's writing style for this contact


@dataclass(frozen=True, slots=True)
class BotSetting:
    """Global bot configuration entry."""

    key: str
    value: str
