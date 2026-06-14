"""Private text message handlers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.handlers.incoming import handle_incoming_text

logger = logging.getLogger(__name__)


async def private_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle private text messages sent directly to the bot."""

    if update.effective_chat is None or update.effective_chat.type != "private":
        return
    if update.effective_user is None or update.effective_message is None:
        return

    user_id = update.effective_user.id
    message_text = update.effective_message.text or ""

    async def reply_fn(text: str) -> None:
        await update.effective_message.reply_text(text)

    await handle_incoming_text(
        contact_user_id=user_id,
        message_text=message_text,
        context=context,
        reply_fn=reply_fn,
        sender_is_owner=False,
        contact_display_name=update.effective_user.full_name or None,
    )
