"""HelloMate Telegram bot entrypoint."""

from __future__ import annotations

import logging

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

from app.config import Config, ConfigError
from app.database.sqlite import SQLiteDatabase
from app.handlers.commands import about, help_command, start
from app.handlers.messages import private_text_message
from app.services.greeting_service import GreetingService


logger = logging.getLogger(__name__)


def configure_logging(log_level: str) -> None:
    """Configure process logging."""

    logging.basicConfig(
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        level=getattr(logging, log_level, logging.INFO),
    )


def build_application(config: Config, database: SQLiteDatabase):
    """Build and configure the Telegram application."""

    greeting_service = GreetingService(database, config.timezone)
    application = ApplicationBuilder().token(config.bot_token).build()
    application.bot_data["greeting_service"] = greeting_service
    application.bot_data["greeting_text"] = config.greeting_text

    private_chat = filters.ChatType.PRIVATE
    application.add_handler(CommandHandler("start", start, filters=private_chat))
    application.add_handler(CommandHandler("help", help_command, filters=private_chat))
    application.add_handler(CommandHandler("about", about, filters=private_chat))
    application.add_handler(
        MessageHandler(private_chat & filters.TEXT & ~filters.COMMAND, private_text_message)
    )

    return application


def main() -> None:
    """Run HelloMate with long polling."""

    try:
        config = Config.from_env()
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc

    configure_logging(config.log_level)
    logger.info("Starting HelloMate bot")

    with SQLiteDatabase(config.database_path) as database:
        application = build_application(config, database)
        application.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()

