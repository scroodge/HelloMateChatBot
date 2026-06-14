"""Scheduled greeting jobs."""

from __future__ import annotations

import logging
from datetime import datetime

from telegram.ext import ContextTypes

from app.services.conversation_starter_service import ConversationStarterService
from app.services.greeting_service import GreetingService
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


async def send_scheduled_greetings(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send proactive greetings to users whose hour matches the current time."""

    greeting_service = context.bot_data.get("greeting_service")
    settings_service = context.bot_data.get("settings_service")
    starter_service = context.bot_data.get("starter_service")
    greeting_text = context.bot_data.get("greeting_text", "")
    timezone = context.bot_data.get("timezone")

    if not isinstance(greeting_service, GreetingService):
        logger.error("Greeting service is not configured for scheduled jobs")
        return
    if not isinstance(settings_service, SettingsService):
        logger.error("Settings service is not configured for scheduled jobs")
        return
    if timezone is None:
        logger.error("Timezone is not configured for scheduled jobs")
        return

    now = datetime.now(tz=timezone)
    current_hour = now.hour
    for settings in settings_service.list_all_user_settings():
        if not settings_service.is_greeting_enabled(settings.user_id):
            continue
        if settings.greeting_hour != current_hour:
            continue
        if not greeting_service.should_send_greeting(settings.user_id, now=now):
            continue

        text = greeting_text
        if settings.use_starters and isinstance(starter_service, ConversationStarterService):
            starter = starter_service.pick()
            if starter:
                text = starter

        try:
            await context.bot.send_message(chat_id=settings.user_id, text=text)
            memory_service = context.bot_data.get("memory_service")
            if memory_service is not None:
                memory_service.record_assistant_message(settings.user_id, text, now=now)
        except Exception:
            logger.exception("Failed to send scheduled greeting to user %s", settings.user_id)


def register_greeting_jobs(application, config) -> None:
    """Register the hourly greeting job."""

    if application.job_queue is None:
        logger.warning("Job queue is unavailable; scheduled greetings are disabled")
        return

    application.job_queue.run_repeating(
        send_scheduled_greetings,
        interval=3600,
        first=10,
        name="scheduled_greetings",
    )
