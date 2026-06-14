"""Scheduled greeting jobs."""

from __future__ import annotations

import logging
from datetime import datetime

from telegram.ext import ContextTypes

from app.services.business_service import BusinessService
from app.services.conversation_starter_service import ConversationStarterService
from app.services.greeting_rules_service import GreetingRulesService
from app.services.greeting_service import GreetingService
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


async def _send_greeting(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    text: str,
    now: datetime,
) -> None:
    business_service = context.bot_data.get("business_service")
    business_connection_id: str | None = None
    if isinstance(business_service, BusinessService):
        chat = business_service.get_chat_for_contact(user_id)
        if chat is not None:
            business_connection_id = chat.connection_id

    await context.bot.send_message(
        chat_id=user_id,
        text=text,
        business_connection_id=business_connection_id,
    )
    memory_service = context.bot_data.get("memory_service")
    if memory_service is not None:
        memory_service.record_assistant_message(user_id, text, now=now)


async def send_scheduled_greetings(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send proactive greetings to users whose hour matches the current time."""

    greeting_service = context.bot_data.get("greeting_service")
    greeting_rules_service = context.bot_data.get("greeting_rules_service")
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

    if isinstance(greeting_rules_service, GreetingRulesService):
        user_ids = {rule.user_id for rule in greeting_rules_service.list_enabled_rules()}
        for user_id in user_ids:
            if not settings_service.is_greeting_enabled(user_id):
                continue
            for rule in greeting_rules_service.get_due_rules(user_id, now, require_hour=True):
                try:
                    await _send_greeting(context, user_id, rule.text, now)
                    greeting_rules_service.mark_sent(rule.id, now.date())
                except Exception:
                    logger.exception(
                        "Failed to send scheduled greeting rule %s to user %s",
                        rule.id,
                        user_id,
                    )

    for settings in settings_service.list_all_user_settings():
        if isinstance(greeting_rules_service, GreetingRulesService):
            if greeting_rules_service.has_rules(settings.user_id):
                continue
        if not settings_service.is_greeting_enabled(settings.user_id):
            continue
        if settings.greeting_hour != now.hour:
            continue
        if not greeting_service.should_send_greeting(settings.user_id, settings, now=now):
            continue

        text = settings_service.resolve_greeting_text(
            settings.user_id,
            greeting_text,
            starter_service if isinstance(starter_service, ConversationStarterService) else None,
        )

        try:
            await _send_greeting(context, settings.user_id, text, now)
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
