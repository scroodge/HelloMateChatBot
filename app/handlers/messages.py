"""Private text message handlers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.services.greeting_service import GreetingService

logger = logging.getLogger(__name__)


async def private_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply with the daily greeting once per private-chat user per calendar day."""

    if update.effective_chat is None or update.effective_chat.type != "private":
        return
    if update.effective_user is None or update.effective_message is None:
        return

    greeting_service = context.bot_data.get("greeting_service")
    greeting_text = context.bot_data.get("greeting_text")
    if not isinstance(greeting_service, GreetingService) or not isinstance(greeting_text, str):
        logger.error("Greeting service is not configured")
        return

    user_id = update.effective_user.id
    if greeting_service.should_send_greeting(user_id):
        await update.effective_message.reply_text(greeting_text)

