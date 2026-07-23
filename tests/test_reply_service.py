"""Tests for reply service helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.reply_service import (
    ReplyService,
    _accuracy_directive,
    _contains_cjk,
    _current_user_content,
    build_persona_prompt,
)
from app.services.weather_service import is_weather_query


def test_contains_cjk_detects_chinese_characters() -> None:
    assert _contains_cjk("降水预报对于明斯克来说")
    assert _contains_cjk("Rain in Minsk 降水")


def test_contains_cjk_ignores_cyrillic_and_latin() -> None:
    assert not _contains_cjk("Дожди в Минске возможны во второй половине дня.")
    assert not _contains_cjk("Rain is likely in Minsk this evening.")


def test_build_persona_prompt_uses_informal_russian() -> None:
    prompt = build_persona_prompt("ru", "Way")
    assert "«ты»" in prompt
    assert "«вы»" in prompt
    assert "первое лицо" in prompt
    assert "Way" in prompt
    assert "ботом" in prompt


def test_build_persona_prompt_uses_first_person_english() -> None:
    prompt = build_persona_prompt("en")
    assert "inner voice" in prompt
    assert "first person" in prompt


def test_is_weather_query_reexported_for_reply_flow() -> None:
    assert is_weather_query("когда дождь?")


def test_accuracy_directive_uses_gender_neutral_contact_wording() -> None:
    directive = _accuracy_directive("ru")

    assert "просьбу контакта" in directive
    assert "собеседницы" not in directive


@pytest.mark.asyncio
async def test_build_messages_uses_resolved_persona_prompt() -> None:
    settings_service = MagicMock()
    settings_service.resolve_persona_prompt.return_value = "Custom admin persona"
    settings_service.get_language.return_value = "ru"
    settings_service.get_openness.return_value = "neutral"
    settings_service.get_user_settings.return_value = MagicMock(style_learning_enabled=False)

    profile = MagicMock(display_name="Way")
    profile_service = MagicMock()
    profile_service.get_or_create_profile.return_value = profile

    memory_service = MagicMock()
    memory_service.get_summary.return_value = None
    memory_service.get_style_profile.return_value = None
    memory_service.as_chat_messages.return_value = []

    mood_service = MagicMock()
    mood_service.latest_mood.return_value = None

    llm_service = AsyncMock()
    reply_service = ReplyService(
        llm_service=llm_service,
        memory_service=memory_service,
        mood_service=mood_service,
        profile_service=profile_service,
        settings_service=settings_service,
        enabled=True,
    )

    messages = await reply_service._build_messages(42, "Привет", "ru")

    settings_service.resolve_persona_prompt.assert_called_once_with(42, "ru", "Way")
    assert messages[0]["role"] == "system"
    # Persona is the base of the system prompt; an openness directive is appended last.
    assert messages[0]["content"].startswith("Custom admin persona")


def test_reply_context_is_separated_from_contact_message() -> None:
    content = _current_user_content(
        "Переведи)))",
        "Цитируемое сообщение (Я):\nбаланс так баланс",
        "ru",
    )

    assert "это не новое сообщение контакта" in content
    assert "Цитируемое сообщение (Я)" in content
    assert content.endswith("Новое сообщение контакта:\nПереведи)))")


@pytest.mark.asyncio
async def test_build_messages_adds_accuracy_priority_and_reply_context() -> None:
    settings_service = MagicMock()
    settings_service.resolve_persona_prompt.return_value = "Дерзкая персона"
    settings_service.get_openness.return_value = "open"
    settings_service.get_user_settings.return_value = MagicMock(style_learning_enabled=False)
    profile_service = MagicMock()
    profile_service.get_or_create_profile.return_value = MagicMock(display_name="Ирина")
    memory_service = MagicMock()
    memory_service.get_summary.return_value = None
    memory_service.as_chat_messages.return_value = []
    mood_service = MagicMock()
    mood_service.latest_mood.return_value = None

    service = ReplyService(
        llm_service=AsyncMock(),
        memory_service=memory_service,
        mood_service=mood_service,
        profile_service=profile_service,
        settings_service=settings_service,
        enabled=True,
    )
    messages = await service._build_messages(
        1,
        "Переведи)))",
        "ru",
        reply_context="Цитируемое сообщение (Я):\nбаланс так баланс",
    )

    assert "сначала точно пойми" in messages[0]["content"]
    assert "не восстанавливай пропущенный смысл по догадке" in messages[0]["content"].lower()
    assert "Цитируемое сообщение (Я)" in messages[-1]["content"]


@pytest.mark.asyncio
async def test_build_messages_tracks_live_window_and_quote_as_context_blocks() -> None:
    settings_service = MagicMock()
    settings_service.resolve_persona_prompt.return_value = "Persona"
    settings_service.get_openness.return_value = "neutral"
    settings_service.get_user_settings.return_value = MagicMock(style_learning_enabled=False)
    profile_service = MagicMock()
    profile_service.get_or_create_profile.return_value = MagicMock(display_name="Way")
    memory_service = MagicMock()
    memory_service.get_summary.return_value = None
    memory_service.as_chat_messages.return_value = [{"role": "assistant", "content": "Earlier"}]
    mood_service = MagicMock()
    mood_service.latest_mood.return_value = None
    service = ReplyService(
        llm_service=AsyncMock(),
        memory_service=memory_service,
        mood_service=mood_service,
        profile_service=profile_service,
        settings_service=settings_service,
        enabled=True,
    )

    compiled = await service._compile_context(
        1, "New message", "en", reply_context="Quoted message"
    )
    messages = await service._build_messages(
        1, "New message", "en", reply_context="Quoted message"
    )

    assert {block.kind for block in compiled.blocks} >= {"live_window", "quoted_message"}
    assert "Earlier" not in compiled.system_prompt
    assert messages[1] == {"role": "assistant", "content": "Earlier"}


@pytest.mark.asyncio
async def test_compile_context_records_typed_sources_without_changing_prompt_order() -> None:
    settings_service = MagicMock()
    settings_service.resolve_persona_prompt.return_value = "Персона"
    settings_service.get_openness.return_value = "neutral"
    settings_service.get_user_settings.return_value = MagicMock(style_learning_enabled=False)
    profile_service = MagicMock()
    profile_service.get_or_create_profile.return_value = MagicMock(display_name="Ирина")
    memory_service = MagicMock()
    memory_service.get_summary.return_value = MagicMock(summary="Старый разговор")
    memory_service.as_chat_messages.return_value = []
    mood_service = MagicMock()
    mood_service.latest_mood.return_value = MagicMock(mood=4)

    service = ReplyService(
        llm_service=AsyncMock(),
        memory_service=memory_service,
        mood_service=mood_service,
        profile_service=profile_service,
        settings_service=settings_service,
        enabled=True,
    )

    compiled = await service._compile_context(1, "Привет", "ru")

    assert [block.kind for block in compiled.blocks] == [
        "persona",
        "mood",
        "summary",
        "accuracy_policy",
        "openness_policy",
    ]
    assert compiled.system_prompt.startswith("Персона Последнее настроение: 4/5.")
    assert compiled.system_prompt.endswith("не раскрывай лишних личных подробностей.")


@pytest.mark.asyncio
async def test_context_budget_drops_live_window_and_quote_before_required_policy() -> None:
    settings_service = MagicMock()
    settings_service.resolve_persona_prompt.return_value = "Persona"
    settings_service.get_openness.return_value = "neutral"
    settings_service.get_user_settings.return_value = MagicMock(style_learning_enabled=False)
    profile_service = MagicMock()
    profile_service.get_or_create_profile.return_value = MagicMock(display_name="Way")
    memory_service = MagicMock()
    memory_service.get_summary.return_value = None
    memory_service.as_chat_messages.return_value = [
        {"role": "assistant", "content": "Earlier reply"}
    ]
    mood_service = MagicMock()
    mood_service.latest_mood.return_value = None
    service = ReplyService(
        llm_service=AsyncMock(),
        memory_service=memory_service,
        mood_service=mood_service,
        profile_service=profile_service,
        settings_service=settings_service,
        context_token_budget=1,
        enabled=True,
    )

    messages = await service._build_messages(
        1, "New message", "en", reply_context="Quoted message"
    )

    assert [message["role"] for message in messages] == ["system", "user"]
    assert messages[-1]["content"] == "New message"
    assert "Persona" in messages[0]["content"]
