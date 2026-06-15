"""Tests for business reply mode: resolution, draft_reply, and pipeline routing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.database.db import Database
from app.services.settings_service import (
    DEFAULT_BUSINESS_REPLY_MODE,
    VALID_BUSINESS_REPLY_MODES,
    SettingsService,
)

# ── Mode resolution ────────────────────────────────────────────────────────────


def _make_settings_service(tmp_path) -> tuple[SettingsService, Database]:
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")
    svc = SettingsService(db.settings, default_language="ru", default_greeting_hour=9)
    return svc, db


def test_default_mode_is_suggest(tmp_path) -> None:
    svc, db = _make_settings_service(tmp_path)
    with db:
        assert svc.get_business_reply_mode(1) == "suggest"


def test_global_setting_overrides_default(tmp_path) -> None:
    svc, db = _make_settings_service(tmp_path)
    with db:
        svc.set_bot_setting("business_reply_mode", "auto")
        assert svc.get_business_reply_mode(999) == "auto"


def test_per_contact_overrides_global(tmp_path) -> None:
    svc, db = _make_settings_service(tmp_path)
    with db:
        svc.set_bot_setting("business_reply_mode", "auto")
        svc.set_business_reply_mode(42, "off")
        assert svc.get_business_reply_mode(42) == "off"
        # other users still get the global
        assert svc.get_business_reply_mode(99) == "auto"


def test_per_contact_none_falls_back_to_global(tmp_path) -> None:
    svc, db = _make_settings_service(tmp_path)
    with db:
        svc.set_bot_setting("business_reply_mode", "suggest")
        svc.set_business_reply_mode(42, "off")
        # clearing per-contact override
        svc.set_business_reply_mode(42, None)
        assert svc.get_business_reply_mode(42) == "suggest"


def test_invalid_mode_raises(tmp_path) -> None:
    svc, db = _make_settings_service(tmp_path)
    with db:
        with pytest.raises(ValueError, match="business_reply_mode"):
            svc.set_business_reply_mode(1, "banana")


def test_invalid_global_mode_falls_back_to_default(tmp_path) -> None:
    """A corrupted global setting should not crash — fall back to builtin default."""
    svc, db = _make_settings_service(tmp_path)
    with db:
        svc.set_bot_setting("business_reply_mode", "garbage")
        assert svc.get_business_reply_mode(1) == DEFAULT_BUSINESS_REPLY_MODE


def test_valid_modes_constant() -> None:
    assert VALID_BUSINESS_REPLY_MODES == {"auto", "suggest", "off"}


# ── draft_reply skips memory ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_draft_reply_does_not_record_memory() -> None:
    """draft_reply must not call memory_service.record_assistant_message."""
    from app.services.reply_service import ReplyService

    memory_service = MagicMock()
    llm_service = MagicMock()
    llm_service.complete = AsyncMock(return_value="вот мой ответ")

    svc = ReplyService(
        llm_service=llm_service,
        memory_service=memory_service,
        mood_service=MagicMock(),
        profile_service=MagicMock(),
        settings_service=MagicMock(
            get_language=MagicMock(return_value="ru"),
            resolve_persona_prompt=MagicMock(return_value="Ты бот"),
            get_user_settings=MagicMock(
                return_value=MagicMock(persona_prompt=None, persona_preset=None)
            ),
        ),
        enabled=True,
    )

    with patch.object(svc, "_build_messages", new=AsyncMock(return_value=[
        {"role": "system", "content": "Ты бот"},
        {"role": "user", "content": "привет"},
    ])):
        draft = await svc.draft_reply(1, "привет")

    assert draft == "вот мой ответ"
    memory_service.record_assistant_message.assert_not_called()


@pytest.mark.asyncio
async def test_draft_reply_returns_none_when_disabled() -> None:
    from app.services.reply_service import ReplyService

    svc = ReplyService(
        llm_service=MagicMock(),
        memory_service=MagicMock(),
        mood_service=MagicMock(),
        profile_service=MagicMock(),
        settings_service=MagicMock(),
        enabled=False,
    )
    result = await svc.draft_reply(1, "привет")
    assert result is None


@pytest.mark.asyncio
async def test_draft_reply_returns_none_on_llm_error() -> None:
    from app.services.reply_service import ReplyService

    llm_service = MagicMock()
    llm_service.complete = AsyncMock(side_effect=RuntimeError("LLM down"))

    svc = ReplyService(
        llm_service=llm_service,
        memory_service=MagicMock(),
        mood_service=MagicMock(),
        profile_service=MagicMock(),
        settings_service=MagicMock(
            get_language=MagicMock(return_value="ru"),
        ),
        enabled=True,
    )

    with patch.object(svc, "_build_messages", new=AsyncMock(return_value=[
        {"role": "user", "content": "привет"},
    ])):
        result = await svc.draft_reply(1, "привет")

    assert result is None


# ── Suggestion DM (owner notification) ─────────────────────────────────────────


def _suggest_context_capture():
    """Build a fake context whose bot.send_message records calls."""
    captured = {}

    async def fake_send_message(**kwargs):
        captured.update(kwargs)

    context = MagicMock()
    context.bot.send_message = AsyncMock(side_effect=fake_send_message)
    return context, captured


@pytest.mark.asyncio
async def test_suggestion_short_draft_has_copy_button() -> None:
    from app.handlers.suggest import build_suggest_fn

    context, captured = _suggest_context_capture()
    on_suggest = build_suggest_fn(
        context=context,
        target_user_ids=[100000001],
        contact_display_name="Аня",
        contact_message="привет",
    )
    await on_suggest("привет! как дела?")

    assert captured["chat_id"] == 100000001
    assert "привет! как дела?" in captured["text"]
    # short draft -> copy button present
    assert captured["reply_markup"] is not None


@pytest.mark.asyncio
async def test_suggestion_long_draft_omits_copy_button() -> None:
    """Drafts over 256 chars must NOT attach a CopyTextButton (Telegram rejects it)."""
    from app.handlers.suggest import build_suggest_fn

    context, captured = _suggest_context_capture()
    long_draft = "а" * 300
    on_suggest = build_suggest_fn(
        context=context,
        target_user_ids=[100000001],
        contact_display_name="Аня",
        contact_message="расскажи подробно",
    )
    await on_suggest(long_draft)

    assert captured["chat_id"] == 100000001
    assert long_draft in captured["text"]  # full draft still in the body for copy
    assert captured["reply_markup"] is None  # no button -> no Button_copy_text_invalid


# ── Pipeline routing ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deliver_ai_reply_off_skips_everything() -> None:
    from app.handlers.incoming import _deliver_ai_reply
    from app.services.reply_service import ReplyService

    reply_service = MagicMock(spec=ReplyService)
    reply_service.generate_reply = AsyncMock()
    reply_service.draft_reply = AsyncMock()

    await _deliver_ai_reply(
        contact_user_id=1,
        message_text="hi",
        reply_service=reply_service,
        reply_fn=AsyncMock(),
        reply_mode="off",
        on_suggest=AsyncMock(),
        event_service=None,
    )

    reply_service.generate_reply.assert_not_called()
    reply_service.draft_reply.assert_not_called()


@pytest.mark.asyncio
async def test_deliver_ai_reply_suggest_calls_on_suggest() -> None:
    from app.handlers.incoming import _deliver_ai_reply
    from app.services.reply_service import ReplyService

    reply_service = MagicMock(spec=ReplyService)
    reply_service.draft_reply = AsyncMock(return_value="черновик")

    on_suggest = AsyncMock()
    reply_fn = AsyncMock()

    await _deliver_ai_reply(
        contact_user_id=1,
        message_text="привет",
        reply_service=reply_service,
        reply_fn=reply_fn,
        reply_mode="suggest",
        on_suggest=on_suggest,
        event_service=None,
    )

    reply_service.draft_reply.assert_awaited_once_with(1, "привет")
    on_suggest.assert_awaited_once_with("черновик")
    reply_fn.assert_not_called()


@pytest.mark.asyncio
async def test_deliver_ai_reply_auto_sends_directly() -> None:
    from app.handlers.incoming import _deliver_ai_reply
    from app.services.reply_service import ReplyService

    reply_service = MagicMock(spec=ReplyService)
    reply_service.generate_reply = AsyncMock(return_value="ответ")

    reply_fn = AsyncMock()

    await _deliver_ai_reply(
        contact_user_id=1,
        message_text="привет",
        reply_service=reply_service,
        reply_fn=reply_fn,
        reply_mode="auto",
        on_suggest=None,
        event_service=None,
    )

    reply_service.generate_reply.assert_awaited_once_with(1, "привет")
    reply_fn.assert_awaited_once_with("ответ")


@pytest.mark.asyncio
async def test_deliver_ai_reply_suggest_no_suggest_fn_is_silent() -> None:
    """If on_suggest is None in suggest mode, draft is generated but silently dropped."""
    from app.handlers.incoming import _deliver_ai_reply
    from app.services.reply_service import ReplyService

    reply_service = MagicMock(spec=ReplyService)
    reply_service.draft_reply = AsyncMock(return_value="черновик")

    await _deliver_ai_reply(
        contact_user_id=1,
        message_text="привет",
        reply_service=reply_service,
        reply_fn=AsyncMock(),
        reply_mode="suggest",
        on_suggest=None,  # no callback wired up
        event_service=None,
    )

    reply_service.draft_reply.assert_awaited_once()
