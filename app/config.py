"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _parse_admin_user_ids(raw_value: str) -> set[int]:
    admin_ids: set[int] = set()
    for part in raw_value.split(","):
        value = part.strip()
        if not value:
            continue
        admin_ids.add(int(value))
    return admin_ids


def _parse_bool(raw_value: str, default: bool = False) -> bool:
    if not raw_value:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Config:
    """Runtime configuration for HelloMate."""

    bot_token: str
    timezone: ZoneInfo
    timezone_name: str
    greeting_text: str
    database_path: Path
    log_level: str
    admin_user_ids: set[int]
    default_language: str
    greeting_hour: int
    conversation_starters_path: Path
    memory_window_size: int
    llm_provider: str
    llm_base_url: str
    llm_model: str
    llm_api_key: str
    llm_max_tokens: int
    ai_replies_enabled: bool
    mini_app_url: str
    api_host: str
    api_port: int
    rag_chunk_size: int
    rag_top_k: int

    @classmethod
    def from_env(cls) -> Config:
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

        admin_raw = os.getenv("ADMIN_USER_IDS", "")
        try:
            admin_user_ids = _parse_admin_user_ids(admin_raw)
        except ValueError as exc:
            raise ConfigError("ADMIN_USER_IDS must be comma-separated integers.") from exc

        default_language = os.getenv("DEFAULT_LANGUAGE", "ru").strip() or "ru"
        greeting_hour = int(os.getenv("GREETING_HOUR", "9"))
        if not 0 <= greeting_hour <= 23:
            raise ConfigError("GREETING_HOUR must be between 0 and 23.")

        conversation_starters_path = Path(
            os.getenv("CONVERSATION_STARTERS", "data/starters.json")
        ).expanduser()
        memory_window_size = int(os.getenv("MEMORY_WINDOW_SIZE", "20"))

        llm_provider = os.getenv("LLM_PROVIDER", "ollama").strip().lower() or "ollama"
        llm_base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434").strip()
        llm_model = os.getenv("LLM_MODEL", "llama3.2").strip()
        llm_api_key = os.getenv("LLM_API_KEY", "").strip()
        llm_max_tokens = int(os.getenv("LLM_MAX_TOKENS", "512"))
        ai_replies_enabled = _parse_bool(os.getenv("AI_REPLIES_ENABLED", "false"))

        mini_app_url = os.getenv("MINI_APP_URL", "").strip()
        api_host = os.getenv("API_HOST", "0.0.0.0").strip() or "0.0.0.0"
        api_port = int(os.getenv("API_PORT", "8080"))
        rag_chunk_size = int(os.getenv("RAG_CHUNK_SIZE", "500"))
        rag_top_k = int(os.getenv("RAG_TOP_K", "3"))

        return cls(
            bot_token=bot_token,
            timezone=timezone,
            timezone_name=timezone_name,
            greeting_text=greeting_text,
            database_path=database_path,
            log_level=log_level,
            admin_user_ids=admin_user_ids,
            default_language=default_language,
            greeting_hour=greeting_hour,
            conversation_starters_path=conversation_starters_path,
            memory_window_size=memory_window_size,
            llm_provider=llm_provider,
            llm_base_url=llm_base_url,
            llm_model=llm_model,
            llm_api_key=llm_api_key,
            llm_max_tokens=llm_max_tokens,
            ai_replies_enabled=ai_replies_enabled,
            mini_app_url=mini_app_url,
            api_host=api_host,
            api_port=api_port,
            rag_chunk_size=rag_chunk_size,
            rag_top_k=rag_top_k,
        )
