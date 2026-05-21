"""Command handlers for HelloMate."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start."""

    if update.effective_chat is None or update.effective_chat.type != "private":
        return
    if update.effective_message is None:
        return

    await update.effective_message.reply_text(
        "Привет! Я HelloMate, открытый Telegram-бот для личных чатов. "
        "Напиши мне сообщение, и я раз в день поздороваюсь с тобой."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help."""

    if update.effective_chat is None or update.effective_chat.type != "private":
        return
    if update.effective_message is None:
        return

    await update.effective_message.reply_text(
        "Сейчас я работаю просто: в личном чате отвечаю на первое сообщение дня "
        "и затем молчу до следующего календарного дня."
    )


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /about."""

    if update.effective_chat is None or update.effective_chat.type != "private":
        return
    if update.effective_message is None:
        return

    await update.effective_message.reply_text(
        "HelloMate — open-source Telegram companion bot for private chats. "
        "Phase 1: simple daily greetings with SQLite persistence, Docker deployment, "
        "and a GitHub-ready Python project."
    )

