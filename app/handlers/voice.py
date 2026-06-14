"""Voice message handlers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.services.memory_service import MemoryService
from app.services.reply_service import ReplyService

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
    if not isinstance(reply_service, ReplyService):
        return

    user_id = update.effective_user.id
    try:
        voice_file = await update.effective_message.voice.get_file()
        audio_bytes = bytes(await voice_file.download_as_bytearray())
        transcription = await reply_service.transcribe_voice(llm_provider, audio_bytes)
        if isinstance(memory_service, MemoryService):
            memory_service.record_user_message(user_id, transcription)
        reply = await reply_service.generate_reply(user_id, transcription)
        if reply:
            await update.effective_message.reply_text(reply)
    except Exception:
        logger.exception("Failed to process voice message for user %s", user_id)
