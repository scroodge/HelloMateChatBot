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
    database_url: str
    log_level: str
    admin_user_ids: set[int]
    default_language: str
    greeting_hour: int
    conversation_starters_path: Path
    memory_window_size: int
    context_token_budget: int
    llm_provider: str
    llm_base_url: str
    llm_model: str
    llm_embedding_model: str
    llm_api_key: str
    llm_max_tokens: int
    llm_temperature: float
    ai_replies_enabled: bool
    mini_app_url: str
    mini_app_dev: bool
    api_host: str
    api_port: int
    rag_chunk_size: int
    rag_top_k: int
    weather_city: str
    owner_name: str
    bot_name: str
    business_mode_enabled: bool
    reply_debounce_seconds: float
    summary_enabled: bool
    summary_refresh_interval: int
    summary_max_chars: int
    facts_enabled: bool
    facts_refresh_interval: int
    style_enabled: bool
    style_refresh_interval: int
    style_max_chars: int
    recall_enabled: bool
    recall_top_k: int
    recall_min_chars: int
    recall_min_score: float
    recall_backfill_batch: int

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
        database_url = os.getenv("DATABASE_URL", "").strip() or f"sqlite:///{database_path}"
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
        context_token_budget = int(os.getenv("CONTEXT_TOKEN_BUDGET", "4000"))
        if context_token_budget < 256:
            raise ConfigError("CONTEXT_TOKEN_BUDGET must be at least 256.")

        llm_provider = os.getenv("LLM_PROVIDER", "ollama").strip().lower() or "ollama"
        llm_base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434").strip()
        llm_model = os.getenv("LLM_MODEL", "llama3.2").strip()
        llm_embedding_model = os.getenv("LLM_EMBEDDING_MODEL", "bge-m3:latest").strip()
        llm_api_key = os.getenv("LLM_API_KEY", "").strip()
        llm_max_tokens = int(os.getenv("LLM_MAX_TOKENS", "512"))
        llm_temperature = float(os.getenv("LLM_TEMPERATURE", "0.7"))
        if not 0.0 <= llm_temperature <= 2.0:
            raise ConfigError("LLM_TEMPERATURE must be between 0.0 and 2.0.")
        ai_replies_enabled = _parse_bool(os.getenv("AI_REPLIES_ENABLED", "false"))

        mini_app_url = os.getenv("MINI_APP_URL", "").strip()
        mini_app_dev = _parse_bool(os.getenv("MINI_APP_DEV", "false"))
        api_host = os.getenv("API_HOST", "0.0.0.0").strip() or "0.0.0.0"
        api_port = int(os.getenv("API_PORT", "8080"))
        rag_chunk_size = int(os.getenv("RAG_CHUNK_SIZE", "500"))
        rag_top_k = int(os.getenv("RAG_TOP_K", "3"))
        weather_city = os.getenv("WEATHER_CITY", "Minsk").strip() or "Minsk"
        owner_name = os.getenv("OWNER_NAME", "Owner").strip() or "Owner"
        bot_name = os.getenv("BOT_NAME", "HelloMate").strip() or "HelloMate"
        business_mode_enabled = _parse_bool(
            os.getenv("BUSINESS_MODE_ENABLED", "true"), default=True
        )
        reply_debounce_seconds = float(os.getenv("REPLY_DEBOUNCE_SECONDS", "5"))
        if reply_debounce_seconds < 0:
            raise ConfigError("REPLY_DEBOUNCE_SECONDS must be >= 0.")

        summary_enabled = _parse_bool(os.getenv("SUMMARY_ENABLED", "true"), default=True)
        summary_refresh_interval = int(os.getenv("SUMMARY_REFRESH_INTERVAL", "10"))
        if summary_refresh_interval < 1:
            raise ConfigError("SUMMARY_REFRESH_INTERVAL must be >= 1.")
        summary_max_chars = int(os.getenv("SUMMARY_MAX_CHARS", "1500"))
        if summary_max_chars < 100:
            raise ConfigError("SUMMARY_MAX_CHARS must be >= 100.")

        facts_enabled = _parse_bool(os.getenv("FACTS_ENABLED", "true"), default=True)
        facts_refresh_interval = int(os.getenv("FACTS_REFRESH_INTERVAL", "5"))
        if facts_refresh_interval < 1:
            raise ConfigError("FACTS_REFRESH_INTERVAL must be >= 1.")

        style_enabled = _parse_bool(os.getenv("STYLE_ENABLED", "true"), default=True)
        style_refresh_interval = int(os.getenv("STYLE_REFRESH_INTERVAL", "5"))
        if style_refresh_interval < 1:
            raise ConfigError("STYLE_REFRESH_INTERVAL must be >= 1.")
        style_max_chars = int(os.getenv("STYLE_MAX_CHARS", "800"))
        if style_max_chars < 100:
            raise ConfigError("STYLE_MAX_CHARS must be >= 100.")

        recall_enabled = _parse_bool(os.getenv("RECALL_ENABLED", "true"), default=True)
        recall_top_k = int(os.getenv("RECALL_TOP_K", "3"))
        if recall_top_k < 1:
            raise ConfigError("RECALL_TOP_K must be >= 1.")
        recall_min_chars = int(os.getenv("RECALL_MIN_CHARS", "15"))
        if recall_min_chars < 1:
            raise ConfigError("RECALL_MIN_CHARS must be >= 1.")
        recall_min_score = float(os.getenv("RECALL_MIN_SCORE", "0.5"))
        if not 0.0 <= recall_min_score <= 1.0:
            raise ConfigError("RECALL_MIN_SCORE must be between 0.0 and 1.0.")
        recall_backfill_batch = int(os.getenv("RECALL_BACKFILL_BATCH", "50"))
        if recall_backfill_batch < 1:
            raise ConfigError("RECALL_BACKFILL_BATCH must be >= 1.")

        return cls(
            bot_token=bot_token,
            timezone=timezone,
            timezone_name=timezone_name,
            greeting_text=greeting_text,
            database_path=database_path,
            database_url=database_url,
            log_level=log_level,
            admin_user_ids=admin_user_ids,
            default_language=default_language,
            greeting_hour=greeting_hour,
            conversation_starters_path=conversation_starters_path,
            memory_window_size=memory_window_size,
            context_token_budget=context_token_budget,
            llm_provider=llm_provider,
            llm_base_url=llm_base_url,
            llm_model=llm_model,
            llm_embedding_model=llm_embedding_model,
            llm_api_key=llm_api_key,
            llm_max_tokens=llm_max_tokens,
            llm_temperature=llm_temperature,
            ai_replies_enabled=ai_replies_enabled,
            mini_app_url=mini_app_url,
            mini_app_dev=mini_app_dev,
            api_host=api_host,
            api_port=api_port,
            rag_chunk_size=rag_chunk_size,
            rag_top_k=rag_top_k,
            weather_city=weather_city,
            owner_name=owner_name,
            bot_name=bot_name,
            business_mode_enabled=business_mode_enabled,
            reply_debounce_seconds=reply_debounce_seconds,
            summary_enabled=summary_enabled,
            summary_refresh_interval=summary_refresh_interval,
            summary_max_chars=summary_max_chars,
            facts_enabled=facts_enabled,
            facts_refresh_interval=facts_refresh_interval,
            style_enabled=style_enabled,
            style_refresh_interval=style_refresh_interval,
            style_max_chars=style_max_chars,
            recall_enabled=recall_enabled,
            recall_top_k=recall_top_k,
            recall_min_chars=recall_min_chars,
            recall_min_score=recall_min_score,
            recall_backfill_batch=recall_backfill_batch,
        )
