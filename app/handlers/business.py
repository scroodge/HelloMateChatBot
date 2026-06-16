"""Telegram Business update handlers."""

from __future__ import annotations

import logging

from telegram import Message, Update
from telegram.ext import ContextTypes

from app.handlers.incoming import handle_incoming_text
from app.services.business_service import BusinessService
from app.services.memory_service import MemoryService
from app.services.reply_service import ReplyService
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


def _is_bot_echo(message: Message) -> bool:
    """Return True when the message was sent by a connected business bot."""

    return bool(message.sender_business_bot)


async def business_connection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Persist business connection state when the owner connects or edits the bot."""

    connection = update.business_connection
    if connection is None or connection.user is None:
        return

    business_service = context.bot_data.get("business_service")
    if not isinstance(business_service, BusinessService):
        logger.error("Business service is not configured")
        return

    business_service.save_connection(
        connection_id=connection.id,
        owner_user_id=connection.user.id,
        is_enabled=connection.is_enabled,
    )
    logger.info(
        "Business connection %s for owner %s (enabled=%s)",
        connection.id,
        connection.user.id,
        connection.is_enabled,
    )


async def business_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages in chats managed via Telegram Business."""

    message = update.business_message
    if message is None or message.chat is None:
        return
    if _is_bot_echo(message):
        return

    business_service = context.bot_data.get("business_service")
    if not isinstance(business_service, BusinessService):
        logger.error("Business service is not configured")
        return

    connection_id = message.business_connection_id
    if not connection_id:
        logger.warning("Business message without connection id in chat %s", message.chat.id)
        return

    connection = business_service.get_connection(connection_id)
    if connection is None:
        try:
            live = await context.bot.get_business_connection(connection_id)
        except Exception:
            logger.exception("Failed to fetch business connection %s", connection_id)
            return
        if live.user is None:
            return
        connection = business_service.save_connection(
            connection_id=live.id,
            owner_user_id=live.user.id,
            is_enabled=live.is_enabled,
        )
    if not connection.is_enabled:
        return

    contact_user_id = business_service.contact_user_id(message.chat.id)
    business_service.save_chat(
        chat_id=message.chat.id,
        contact_user_id=contact_user_id,
        connection_id=connection_id,
    )

    sender_id = message.from_user.id if message.from_user is not None else None
    sender_is_owner = business_service.is_owner_message(connection.owner_user_id, sender_id)
    contact_display_name = None
    if not sender_is_owner and message.from_user is not None:
        contact_display_name = message.from_user.full_name

    if message.text:
        if sender_is_owner:

            async def owner_reply_fn(text: str) -> None:
                # reply_text auto-forwards the message's own business_connection_id
                await message.reply_text(text)

            await handle_incoming_text(
                contact_user_id=contact_user_id,
                message_text=message.text,
                context=context,
                reply_fn=owner_reply_fn,
                sender_is_owner=True,
                contact_display_name=contact_display_name,
            )
            return

        # Contact message — resolve reply mode
        settings_service = context.bot_data.get("settings_service")
        reply_mode = "auto"
        if isinstance(settings_service, SettingsService):
            reply_mode = settings_service.get_business_reply_mode(contact_user_id)
        logger.info(
            "business contact message from %s, resolved reply_mode=%s",
            contact_user_id,
            reply_mode,
        )

        async def reply_fn(text: str) -> None:
            await message.reply_text(text)

        await handle_incoming_text(
            contact_user_id=contact_user_id,
            message_text=message.text,
            context=context,
            reply_fn=reply_fn,
            sender_is_owner=False,
            contact_display_name=contact_display_name,
            reply_mode=reply_mode,
        )
        return

    if message.voice is not None and not sender_is_owner:
        await _handle_business_voice(
            message=message,
            contact_user_id=contact_user_id,
            owner_user_id=connection.owner_user_id,
            context=context,
        )


async def _handle_business_voice(
    message: Message,
    contact_user_id: int,
    owner_user_id: int,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    reply_service = context.bot_data.get("reply_service")
    llm_provider = context.bot_data.get("llm_provider")
    memory_service = context.bot_data.get("memory_service")
    settings_service = context.bot_data.get("settings_service")
    if not isinstance(reply_service, ReplyService) or message.voice is None:
        return

    reply_mode = "auto"
    if isinstance(settings_service, SettingsService):
        reply_mode = settings_service.get_business_reply_mode(contact_user_id)

    if reply_mode == "off":
        return

    try:
        voice_file = await message.voice.get_file()
        audio_bytes = bytes(await voice_file.download_as_bytearray())
        transcription = await reply_service.transcribe_voice(llm_provider, audio_bytes)
        if isinstance(memory_service, MemoryService):
            memory_service.record_user_message(contact_user_id, transcription)

        if reply_mode == "suggest":
            draft = await reply_service.draft_reply(contact_user_id, transcription)
            if draft:
                # Store in the Suggest Inbox (Mini App) only — nothing sent to chat.
                suggestions_service = context.bot_data.get("suggestions_service")
                if suggestions_service is not None:
                    suggestions_service.record(
                        contact_user_id, f"🎤 {transcription}", draft
                    )
        else:
            reply = await reply_service.generate_reply(contact_user_id, transcription)
            if reply:
                await message.reply_text(reply)
    except Exception:
        logger.exception("Failed to process business voice message for contact %s", contact_user_id)
