"""The direct bot-chat path must honour business_reply_mode (never auto-send by default).

Regression: copying a suggestion and sending it back into the bot DM (or any
direct message) used to trigger an automatic reply because the direct handler
hardcoded reply_mode="auto", bypassing the per-contact suggest setting.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.database.db import Database
from app.handlers import messages as messages_handler
from app.services.settings_service import SettingsService


def _make_update(user_id: int, text: str):
    update = MagicMock()
    update.effective_chat.type = "private"
    update.effective_user.id = user_id
    update.effective_user.full_name = "Тестовый"
    update.effective_message.text = text
    update.effective_message.reply_text = AsyncMock()
    return update


def _make_context(settings_service: SettingsService, admin_ids: set[int]):
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot_data = {
        "settings_service": settings_service,
        "admin_user_ids": admin_ids,
    }
    return context


@pytest.mark.asyncio
async def test_direct_suggest_passes_suggest_mode_and_builds_callback(tmp_path) -> None:
    db = Database(f"sqlite:///{tmp_path / 'direct.db'}")
    db.open()
    with db:
        settings = SettingsService(db.settings, default_language="ru", default_greeting_hour=9)
        update = _make_update(555, "привет")  # default mode = suggest
        context = _make_context(settings, admin_ids={100000001})

        with patch.object(messages_handler, "handle_incoming_text", new=AsyncMock()) as mock_pipe:
            await messages_handler.private_text_message(update, context)

        kwargs = mock_pipe.await_args.kwargs
        assert kwargs["reply_mode"] == "suggest"
        assert kwargs["on_suggest"] is not None  # admin DM callback wired up
        assert kwargs["sender_is_owner"] is False


@pytest.mark.asyncio
async def test_direct_auto_passes_auto_and_no_suggest(tmp_path) -> None:
    db = Database(f"sqlite:///{tmp_path / 'direct.db'}")
    db.open()
    with db:
        settings = SettingsService(db.settings, default_language="ru", default_greeting_hour=9)
        settings.set_business_reply_mode(555, "auto")
        update = _make_update(555, "привет")
        context = _make_context(settings, admin_ids={100000001})

        with patch.object(messages_handler, "handle_incoming_text", new=AsyncMock()) as mock_pipe:
            await messages_handler.private_text_message(update, context)

        kwargs = mock_pipe.await_args.kwargs
        assert kwargs["reply_mode"] == "auto"
        assert kwargs["on_suggest"] is None


@pytest.mark.asyncio
async def test_direct_off_passes_off_mode(tmp_path) -> None:
    db = Database(f"sqlite:///{tmp_path / 'direct.db'}")
    db.open()
    with db:
        settings = SettingsService(db.settings, default_language="ru", default_greeting_hour=9)
        settings.set_business_reply_mode(555, "off")
        update = _make_update(555, "привет")
        context = _make_context(settings, admin_ids={100000001})

        with patch.object(messages_handler, "handle_incoming_text", new=AsyncMock()) as mock_pipe:
            await messages_handler.private_text_message(update, context)

        kwargs = mock_pipe.await_args.kwargs
        assert kwargs["reply_mode"] == "off"
        assert kwargs["on_suggest"] is None


@pytest.mark.asyncio
async def test_greeting_suppressed_outside_auto_mode() -> None:
    """In suggest/off mode the greeting must not be auto-sent to the contact."""
    from app.handlers import incoming
    from app.services.greeting_service import GreetingService
    from app.services.reply_service import ReplyService

    reply_fn = AsyncMock()
    settings_service = MagicMock(spec=SettingsService)
    settings_service.is_greeting_enabled.return_value = True  # greetings ON ...

    reply_service = MagicMock(spec=ReplyService)
    reply_service.draft_reply = AsyncMock(return_value="черновик")
    reply_service.generate_reply = AsyncMock(return_value="ответ")

    context = MagicMock()
    context.bot_data = {
        "settings_service": settings_service,
        "greeting_service": MagicMock(spec=GreetingService),
        "greeting_text": "привет!",
        "reply_service": reply_service,
    }
    on_suggest = AsyncMock()

    await incoming._process_incoming_text(
        contact_user_id=1,
        message_text="привет",
        context=context,
        reply_fn=reply_fn,
        sender_is_owner=False,
        reply_mode="suggest",  # ... but mode is suggest
        on_suggest=on_suggest,
    )

    # No greeting (or any message) was pushed to the contact directly.
    reply_fn.assert_not_called()
    # The reply was routed as a suggestion instead.
    on_suggest.assert_awaited_once_with("черновик")
