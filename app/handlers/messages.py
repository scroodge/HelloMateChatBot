"""Private text message handlers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.services.conversation_starter_service import ConversationStarterService
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
    settings_service = context.bot_data.get("settings_service")
    starter_service = context.bot_data.get("starter_service")
    memory_service = context.bot_data.get("memory_service")
    profile_service = context.bot_data.get("profile_service")
    reply_service = context.bot_data.get("reply_service")
    greeting_text = context.bot_data.get("greeting_text", "")

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
    if greeting_service.should_send_greeting(user_id):
        text = greeting_text
        settings = settings_service.get_user_settings(user_id)
        if settings.use_starters and isinstance(starter_service, ConversationStarterService):
            starter = starter_service.pick()
            if starter:
                text = starter

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
