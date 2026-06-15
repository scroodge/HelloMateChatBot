"""Shared helper for delivering reply suggestions to the owner/admins.

Suggest mode must NEVER send a message to the contact — the draft is only
DM'd to the owner (Business) or admins (direct chat), who copy/paste it
manually. This module centralises that delivery so every entry point shares
the exact same behavior and formatting.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from telegram import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

ReplyFn = Callable[[str], Awaitable[None]]

# Telegram API limit for InlineKeyboardButton.copy_text (CopyTextButton.text)
COPY_TEXT_MAX_LEN = 256


def _format_notification(contact_display_name: str, contact_message: str, draft: str) -> str:
    # Plain text (no parse_mode) so contact names / drafts can't break Markdown.
    return f"💬 {contact_display_name}:\n" f"{contact_message}\n\n" f"✏️ Готовый ответ:\n" f"{draft}"


def build_suggest_fn(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    target_user_ids: list[int],
    contact_display_name: str,
    contact_message: str,
) -> ReplyFn:
    """Return an on_suggest callback that DMs the draft to each target user.

    The draft is delivered with a copy button when short enough; longer drafts
    are copied from the message body directly (Telegram rejects oversized
    CopyTextButton text).
    """

    async def _send_suggestion(draft: str) -> None:
        notification = _format_notification(contact_display_name, contact_message, draft)
        reply_markup = None
        if 1 <= len(draft) <= COPY_TEXT_MAX_LEN:
            reply_markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text="📋 Скопировать ответ",
                            copy_text=CopyTextButton(text=draft),
                        )
                    ]
                ]
            )
        for target_id in target_user_ids:
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=notification,
                    reply_markup=reply_markup,
                )
            except Exception:
                logger.exception("Failed to send suggestion DM to %s", target_id)

    return _send_suggestion
