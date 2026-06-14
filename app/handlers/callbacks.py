"""Callback query handlers."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.handlers.mood import mood_callback


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route callback queries to feature handlers."""

    if update.callback_query is None:
        return

    data = update.callback_query.data or ""
    if data.startswith("mood:"):
        await mood_callback(update, context)
