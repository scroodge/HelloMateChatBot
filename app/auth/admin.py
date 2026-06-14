"""Admin authorization helpers."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.i18n import translate


def is_admin(user_id: int, admin_user_ids: set[int]) -> bool:
    """Return True when the Telegram user is configured as an admin."""

    return user_id in admin_user_ids


async def require_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Return False and notify the user when they are not an admin."""

    if update.effective_user is None or update.effective_message is None:
        return False

    admin_user_ids = context.bot_data.get("admin_user_ids", set())
    settings_service = context.bot_data.get("settings_service")
    language = "ru"
    if settings_service is not None:
        language = settings_service.get_language(update.effective_user.id)

    if not isinstance(admin_user_ids, set) or not is_admin(
        update.effective_user.id, admin_user_ids
    ):
        await update.effective_message.reply_text(translate("admin_only", language))
        return False
    return True
