"""Mood command and callback handlers."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.handlers.helpers import get_language
from app.i18n import translate
from app.services.mood_service import MoodService


def _mood_keyboard(language: str) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(str(value), callback_data=f"mood:{value}") for value in range(1, 6)
    ]
    return InlineKeyboardMarkup([buttons])


async def mood_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /mood."""

    if update.effective_chat is None or update.effective_chat.type != "private":
        return
    if update.effective_message is None:
        return

    language = get_language(update, context)
    await update.effective_message.reply_text(
        translate("mood_prompt", language),
        reply_markup=_mood_keyboard(language),
    )


async def mood_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /moodhistory."""

    if update.effective_chat is None or update.effective_chat.type != "private":
        return
    if update.effective_message is None or update.effective_user is None:
        return

    mood_service = context.bot_data.get("mood_service")
    if not isinstance(mood_service, MoodService):
        return

    language = get_language(update, context)
    entries = mood_service.recent_entries(update.effective_user.id, limit=7)
    if not entries:
        await update.effective_message.reply_text(translate("mood_history_empty", language))
        return

    lines = [translate("mood_history_title", language)]
    for entry in entries:
        note = entry.note or ""
        lines.append(
            translate(
                "mood_history_item",
                language,
                date=entry.recorded_at.strftime("%Y-%m-%d"),
                mood=entry.mood,
                note=note,
            )
        )
    await update.effective_message.reply_text("\n".join(lines))


async def mood_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline mood button presses."""

    if update.callback_query is None or update.effective_user is None:
        return

    mood_service = context.bot_data.get("mood_service")
    if not isinstance(mood_service, MoodService):
        return

    data = update.callback_query.data or ""
    if not data.startswith("mood:"):
        return

    mood_value = int(data.split(":", maxsplit=1)[1])
    mood_service.record_mood(update.effective_user.id, mood_value)
    language = get_language(update, context)
    await update.callback_query.answer()
    if update.callback_query.message is not None:
        await update.callback_query.message.reply_text(
            translate("mood_saved", language, mood=mood_value)
        )
