"""Tests for reply service helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.reply_service import ReplyService, _contains_cjk, build_persona_prompt
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


@pytest.mark.asyncio
async def test_build_messages_uses_resolved_persona_prompt() -> None:
    settings_service = MagicMock()
    settings_service.resolve_persona_prompt.return_value = "Custom admin persona"
    settings_service.get_language.return_value = "ru"

    profile = MagicMock(display_name="Way")
    profile_service = MagicMock()
    profile_service.get_or_create_profile.return_value = profile

    memory_service = MagicMock()
    memory_service.get_summary.return_value = None
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
    assert messages[0]["content"] == "Custom admin persona"
