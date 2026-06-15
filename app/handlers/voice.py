"""Voice message handlers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.handlers.suggest import build_suggest_fn
from app.services.memory_service import MemoryService
from app.services.reply_service import ReplyService
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


async def private_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Transcribe voice messages and route them through the reply service."""

    if update.effective_chat is None or update.effective_chat.type != "private":
        return
    if update.effective_user is None or update.effective_message is None:
        return
    if update.effective_message.voice is None:
        return

    reply_service = context.bot_data.get("reply_service")
    llm_provider = context.bot_data.get("llm_provider")
    memory_service = context.bot_data.get("memory_service")
    settings_service = context.bot_data.get("settings_service")
    if not isinstance(reply_service, ReplyService):
        return

    user_id = update.effective_user.id

    # Mirror the text path: never auto-answer unless the resolved mode is "auto".
    reply_mode = "auto"
    if isinstance(settings_service, SettingsService):
        reply_mode = settings_service.get_business_reply_mode(user_id)

    if reply_mode == "off":
        return

    try:
        voice_file = await update.effective_message.voice.get_file()
        audio_bytes = bytes(await voice_file.download_as_bytearray())
        transcription = await reply_service.transcribe_voice(llm_provider, audio_bytes)
        if isinstance(memory_service, MemoryService):
            memory_service.record_user_message(user_id, transcription)

        if reply_mode == "suggest":
            admin_ids = sorted(context.bot_data.get("admin_user_ids", set()))
            if not admin_ids:
                return
            draft = await reply_service.draft_reply(user_id, transcription)
            if draft:
                on_suggest = build_suggest_fn(
                    context=context,
                    target_user_ids=admin_ids,
                    contact_display_name=update.effective_user.full_name or str(user_id),
                    contact_message=f"🎤 {transcription}",
                )
                await on_suggest(draft)
            return

        reply = await reply_service.generate_reply(user_id, transcription)
        if reply:
            await update.effective_message.reply_text(reply)
    except Exception:
        logger.exception("Failed to process voice message for user %s", user_id)
