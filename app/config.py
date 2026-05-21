"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class Config:
    """Runtime configuration for HelloMate."""

    bot_token: str
    timezone: ZoneInfo
    timezone_name: str
    greeting_text: str
    database_path: Path
    log_level: str

    @classmethod
    def from_env(cls) -> "Config":
        """Build configuration from environment variables."""

        load_dotenv()

        bot_token = os.getenv("BOT_TOKEN", "").strip()
        if not bot_token:
            raise ConfigError("BOT_TOKEN is required. Set it in your .env file.")
        if ":" not in bot_token:
            raise ConfigError("BOT_TOKEN looks invalid. Use the token provided by BotFather.")

        timezone_name = os.getenv("TIMEZONE", "Europe/Minsk").strip() or "Europe/Minsk"
        try:
            timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ConfigError(f"Invalid TIMEZONE: {timezone_name}") from exc

        greeting_text = os.getenv("GREETING_TEXT", "Привет друг! Как ты)")
        database_path = Path(os.getenv("DATABASE_PATH", "/app/data/hellomate.db")).expanduser()
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()

        return cls(
            bot_token=bot_token,
            timezone=timezone,
            timezone_name=timezone_name,
            greeting_text=greeting_text,
            database_path=database_path,
            log_level=log_level,
        )
