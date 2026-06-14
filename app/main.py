"""HelloMate Telegram bot entrypoint."""

from __future__ import annotations

import logging
import threading

import uvicorn
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from app.api.main import create_api_app
from app.config import Config, ConfigError
from app.database.sqlite import SQLiteDatabase
from app.handlers.admin import (
    addgreeting_command,
    admin_help,
    delgreeting_command,
    listgreetings_command,
    setgreeting_command,
    setgreettext_command,
    setgreetschedule_command,
    sethour_command,
    getpersona_command,
    setlang_command,
    setpersona_command,
    setstarters_command,
    settings_command,
    togglegreeting_command,
    userinfo_command,
)
from app.handlers.callbacks import callback_router
from app.handlers.commands import (
    about,
    dashboard_command,
    help_command,
    lang_command,
    profile_command,
    remember_command,
    setname_command,
    start,
)
from app.handlers.messages import private_text_message
from app.handlers.mood import mood_command, mood_history_command
from app.handlers.voice import private_voice_message
from app.jobs.greeting_jobs import register_greeting_jobs
from app.services.conversation_starter_service import ConversationStarterService
from app.services.embedding_service import EmbeddingService
from app.services.greeting_rules_service import GreetingRulesService
from app.services.greeting_service import GreetingService
from app.services.llm import LLMService
from app.services.llm.factory import build_llm_provider
from app.services.memory_service import MemoryService
from app.services.mood_service import MoodService
from app.services.profile_service import ProfileService
from app.services.rag_service import RAGService
from app.services.reply_service import ReplyService
from app.services.settings_service import SettingsService
from app.services.weather_service import WeatherService

logger = logging.getLogger(__name__)


def configure_logging(log_level: str) -> None:
    """Configure process logging."""

    logging.basicConfig(
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        level=getattr(logging, log_level, logging.INFO),
    )


def build_application(config: Config, database: SQLiteDatabase):
    """Build and configure the Telegram application."""

    greeting_service = GreetingService(database.greetings, config.timezone)
    greeting_rules_service = GreetingRulesService(database.greeting_rules)
    settings_service = SettingsService(
        database.settings,
        config.default_language,
        config.greeting_hour,
    )
    starter_service = ConversationStarterService(config.conversation_starters_path)
    profile_service = ProfileService(database.profiles, config.timezone_name)
    mood_service = MoodService(database.moods)
    memory_service = MemoryService(database.memory, config.memory_window_size)
    llm_provider = build_llm_provider(config)
    llm_service = LLMService(llm_provider)
    embedding_service = EmbeddingService(
        base_url=config.llm_base_url,
        model=config.llm_embedding_model,
        api_key=config.llm_api_key,
        provider=config.llm_provider,
    )
    rag_service = RAGService(
        database.documents,
        embedding_service,
        chunk_size=config.rag_chunk_size,
        top_k=config.rag_top_k,
    )
    weather_service = WeatherService(config.weather_city, config.timezone)
    reply_service = ReplyService(
        llm_service=llm_service,
        memory_service=memory_service,
        mood_service=mood_service,
        profile_service=profile_service,
        settings_service=settings_service,
        rag_service=rag_service,
        weather_service=weather_service,
        enabled=config.ai_replies_enabled,
    )

    application = ApplicationBuilder().token(config.bot_token).build()
    application.bot_data["greeting_service"] = greeting_service
    application.bot_data["greeting_rules_service"] = greeting_rules_service
    application.bot_data["settings_service"] = settings_service
    application.bot_data["starter_service"] = starter_service
    application.bot_data["profile_service"] = profile_service
    application.bot_data["mood_service"] = mood_service
    application.bot_data["memory_service"] = memory_service
    application.bot_data["reply_service"] = reply_service
    application.bot_data["rag_service"] = rag_service
    application.bot_data["llm_provider"] = llm_provider
    application.bot_data["greeting_text"] = config.greeting_text
    application.bot_data["timezone"] = config.timezone
    application.bot_data["admin_user_ids"] = config.admin_user_ids
    application.bot_data["default_language"] = config.default_language
    application.bot_data["mini_app_url"] = config.mini_app_url

    private_chat = filters.ChatType.PRIVATE
    application.add_handler(CommandHandler("start", start, filters=private_chat))
    application.add_handler(CommandHandler("help", help_command, filters=private_chat))
    application.add_handler(CommandHandler("about", about, filters=private_chat))
    application.add_handler(CommandHandler("lang", lang_command, filters=private_chat))
    application.add_handler(CommandHandler("profile", profile_command, filters=private_chat))
    application.add_handler(CommandHandler("setname", setname_command, filters=private_chat))
    application.add_handler(CommandHandler("mood", mood_command, filters=private_chat))
    application.add_handler(
        CommandHandler("moodhistory", mood_history_command, filters=private_chat)
    )
    application.add_handler(CommandHandler("remember", remember_command, filters=private_chat))
    application.add_handler(CommandHandler("dashboard", dashboard_command, filters=private_chat))
    application.add_handler(CommandHandler("admin", admin_help, filters=private_chat))
    application.add_handler(CommandHandler("settings", settings_command, filters=private_chat))
    application.add_handler(CommandHandler("setlang", setlang_command, filters=private_chat))
    application.add_handler(
        CommandHandler("setgreeting", setgreeting_command, filters=private_chat)
    )
    application.add_handler(
        CommandHandler("setgreettext", setgreettext_command, filters=private_chat)
    )
    application.add_handler(
        CommandHandler("setgreetschedule", setgreetschedule_command, filters=private_chat)
    )
    application.add_handler(CommandHandler("greetings", listgreetings_command, filters=private_chat))
    application.add_handler(CommandHandler("addgreeting", addgreeting_command, filters=private_chat))
    application.add_handler(CommandHandler("delgreeting", delgreeting_command, filters=private_chat))
    application.add_handler(
        CommandHandler("togglegreeting", togglegreeting_command, filters=private_chat)
    )
    application.add_handler(
        CommandHandler("setstarters", setstarters_command, filters=private_chat)
    )
    application.add_handler(CommandHandler("sethour", sethour_command, filters=private_chat))
    application.add_handler(CommandHandler("setpersona", setpersona_command, filters=private_chat))
    application.add_handler(CommandHandler("getpersona", getpersona_command, filters=private_chat))
    application.add_handler(CommandHandler("userinfo", userinfo_command, filters=private_chat))
    application.add_handler(CallbackQueryHandler(callback_router))
    application.add_handler(
        MessageHandler(private_chat & filters.TEXT & ~filters.COMMAND, private_text_message)
    )
    application.add_handler(MessageHandler(private_chat & filters.VOICE, private_voice_message))

    register_greeting_jobs(application, config)
    return application


def _start_api_server(config: Config, database: SQLiteDatabase) -> threading.Thread:
    api_app = create_api_app(config, database)
    thread = threading.Thread(
        target=uvicorn.run,
        kwargs={
            "app": api_app,
            "host": config.api_host,
            "port": config.api_port,
            "log_level": config.log_level.lower(),
        },
        daemon=True,
    )
    thread.start()
    return thread


def main() -> None:
    """Run HelloMate with long polling and optional API server."""

    try:
        config = Config.from_env()
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc

    configure_logging(config.log_level)
    logger.info("Starting HelloMate bot")

    with SQLiteDatabase(config.database_path) as database:
        if config.mini_app_url:
            _start_api_server(config, database)
            logger.info("API server started on %s:%s", config.api_host, config.api_port)

        application = build_application(config, database)
        application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
