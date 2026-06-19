"""Shared handler helpers."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.i18n import translate
from app.services.settings_service import SettingsService


def get_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Return the effective language for the current user."""

    settings_service = context.bot_data.get("settings_service")
    if update.effective_user is None or not isinstance(settings_service, SettingsService):
        return context.bot_data.get("default_language", "ru")
    return settings_service.get_language(update.effective_user.id)


def is_business_update(update: Update) -> bool:
    """Return True for Telegram Business messages, even in private chats."""

    if update.business_message is not None or update.edited_business_message is not None:
        return True
    message = update.effective_message
    return bool(message is not None and message.business_connection_id)


async def reply(
    update: Update,
    key: str,
    context: ContextTypes.DEFAULT_TYPE,
    **kwargs: object,
) -> None:
    """Reply with a localized string."""

    if update.effective_message is None:
        return
    language = get_language(update, context)
    await update.effective_message.reply_text(translate(key, language, **kwargs))
