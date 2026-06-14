"""Private text message handlers."""

from __future__ import annotations

import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from app.services.conversation_starter_service import ConversationStarterService
from app.services.greeting_rules_service import GreetingRulesService
from app.services.greeting_service import GreetingService
from app.services.memory_service import MemoryService
from app.services.profile_service import ProfileService
from app.services.reply_service import ReplyService
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


async def private_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle private text messages with greetings, memory, and optional AI replies."""

    if update.effective_chat is None or update.effective_chat.type != "private":
        return
    if update.effective_user is None or update.effective_message is None:
        return

    greeting_service = context.bot_data.get("greeting_service")
    greeting_rules_service = context.bot_data.get("greeting_rules_service")
    settings_service = context.bot_data.get("settings_service")
    starter_service = context.bot_data.get("starter_service")
    memory_service = context.bot_data.get("memory_service")
    profile_service = context.bot_data.get("profile_service")
    reply_service = context.bot_data.get("reply_service")
    greeting_text = context.bot_data.get("greeting_text", "")
    timezone = context.bot_data.get("timezone")

    if not isinstance(greeting_service, GreetingService):
        logger.error("Greeting service is not configured")
        return
    if not isinstance(settings_service, SettingsService):
        logger.error("Settings service is not configured")
        return
    if not isinstance(greeting_text, str):
        logger.error("Greeting text is not configured")
        return

    user_id = update.effective_user.id
    message_text = update.effective_message.text or ""

    if isinstance(profile_service, ProfileService):
        profile_service.get_or_create_profile(
            user_id,
            display_name=update.effective_user.full_name or None,
        )

    if isinstance(memory_service, MemoryService) and message_text:
        memory_service.record_user_message(user_id, message_text)

    if not settings_service.is_greeting_enabled(user_id):
        if isinstance(reply_service, ReplyService):
            reply = await reply_service.generate_reply(user_id, message_text)
            if reply:
                await update.effective_message.reply_text(reply)
        return

    sent_greeting = False
    now = datetime.now(tz=timezone) if timezone is not None else datetime.now()

    if isinstance(greeting_rules_service, GreetingRulesService) and greeting_rules_service.has_rules(
        user_id
    ):
        due_rules = greeting_rules_service.get_due_rules(user_id, now, require_hour=False)
        if due_rules:
            rule = due_rules[0]
            await update.effective_message.reply_text(rule.text)
            if isinstance(memory_service, MemoryService):
                memory_service.record_assistant_message(user_id, rule.text)
            greeting_rules_service.mark_sent(rule.id, now.date())
            sent_greeting = True
    else:
        user_settings = settings_service.get_user_settings(user_id)
        if greeting_service.should_send_greeting(user_id, user_settings, now=now):
            text = settings_service.resolve_greeting_text(
                user_id,
                greeting_text,
                starter_service if isinstance(starter_service, ConversationStarterService) else None,
            )

            await update.effective_message.reply_text(text)
            if isinstance(memory_service, MemoryService):
                memory_service.record_assistant_message(user_id, text)
            sent_greeting = True

    if sent_greeting:
        return

    if isinstance(reply_service, ReplyService):
        reply = await reply_service.generate_reply(user_id, message_text)
        if reply:
            await update.effective_message.reply_text(reply)
