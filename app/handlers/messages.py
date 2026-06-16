"""Private text message handlers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.auth.admin import is_admin
from app.handlers.incoming import handle_incoming_text
from app.services.assistant_service import AssistantService
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


async def private_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle private text messages sent directly to the bot."""

    if update.effective_chat is None or update.effective_chat.type != "private":
        return
    if update.effective_user is None or update.effective_message is None:
        return

    user_id = update.effective_user.id
    message_text = update.effective_message.text or ""

    # Owner personal-assistant mode: when the owner has an active assistant
    # profile, their direct messages are answered by that assistant (isolated
    # memory), bypassing the contact pipeline entirely.
    admin_user_ids = context.bot_data.get("admin_user_ids", set())
    assistant_service = context.bot_data.get("assistant_service")
    if (
        isinstance(admin_user_ids, set)
        and is_admin(user_id, admin_user_ids)
        and isinstance(assistant_service, AssistantService)
        and assistant_service.is_active(user_id)
        and message_text
    ):
        reply = await assistant_service.reply(user_id, message_text)
        if reply:
            await update.effective_message.reply_text(reply)
        return

    # Respect the contact's reply mode here too: a direct chat must never get an
    # automatic reply unless the resolved mode is explicitly "auto". The default
    # is "suggest", so by default the bot only stores a draft in the Suggest
    # Inbox (Mini App) — it never answers the person on its own.
    settings_service = context.bot_data.get("settings_service")
    reply_mode = "auto"
    if isinstance(settings_service, SettingsService):
        reply_mode = settings_service.get_business_reply_mode(user_id)

    async def reply_fn(text: str) -> None:
        await update.effective_message.reply_text(text)

    await handle_incoming_text(
        contact_user_id=user_id,
        message_text=message_text,
        context=context,
        reply_fn=reply_fn,
        sender_is_owner=False,
        contact_display_name=update.effective_user.full_name or None,
        reply_mode=reply_mode,
    )
