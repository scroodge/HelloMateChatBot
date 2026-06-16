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
        event_service=None,
    )

    reply_service.generate_reply.assert_not_called()
    reply_service.draft_reply.assert_not_called()


@pytest.mark.asyncio
async def test_deliver_ai_reply_suggest_records_to_inbox_no_chat_message() -> None:
    """Suggest mode stores the draft in the inbox and never writes to the chat."""
    from app.handlers.incoming import _deliver_ai_reply
    from app.services.reply_service import ReplyService

    reply_service = MagicMock(spec=ReplyService)
    reply_service.draft_reply = AsyncMock(return_value="черновик")

    suggestions_service = MagicMock()
    reply_fn = AsyncMock()

    await _deliver_ai_reply(
        contact_user_id=1,
        message_text="привет",
        reply_service=reply_service,
        reply_fn=reply_fn,
        reply_mode="suggest",
        event_service=None,
        suggestions_service=suggestions_service,
    )

    reply_service.draft_reply.assert_awaited_once_with(1, "привет")
    suggestions_service.record.assert_called_once_with(1, "привет", "черновик")
    reply_fn.assert_not_called()  # nothing sent to the chat


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
        event_service=None,
    )

    reply_service.generate_reply.assert_awaited_once_with(1, "привет")
    reply_fn.assert_awaited_once_with("ответ")


@pytest.mark.asyncio
async def test_deliver_ai_reply_suggest_no_service_is_silent() -> None:
    """If no suggestions_service is wired up, the draft is generated but dropped."""
    from app.handlers.incoming import _deliver_ai_reply
    from app.services.reply_service import ReplyService

    reply_service = MagicMock(spec=ReplyService)
    reply_service.draft_reply = AsyncMock(return_value="черновик")
    reply_fn = AsyncMock()

    await _deliver_ai_reply(
        contact_user_id=1,
        message_text="привет",
        reply_service=reply_service,
        reply_fn=reply_fn,
        reply_mode="suggest",
        event_service=None,
        suggestions_service=None,
    )

    reply_service.draft_reply.assert_awaited_once()
    reply_fn.assert_not_called()
