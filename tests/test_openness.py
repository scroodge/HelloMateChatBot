"""Tests for the per-contact openness dial and its prompt injection (Phase 12)."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.database.db import Database
from app.services.memory_service import MemoryService
from app.services.mood_service import MoodService
from app.services.profile_service import ProfileService
from app.services.reply_service import ReplyService, _openness_directive
from app.services.settings_service import (
    DEFAULT_OPENNESS,
    OPENNESS_SETTING,
    SettingsService,
)


def _build_services(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'open.db'}")
    db.open()
    settings = SettingsService(db.settings, "ru", 9)
    memory = MemoryService(db.memory, window_size=20)
    mood = MoodService(db.moods)
    profile = ProfileService(db.profiles, "Europe/Minsk")
    llm = MagicMock()
    llm.complete = AsyncMock(return_value="ответ")
    reply = ReplyService(
        llm_service=llm,
        memory_service=memory,
        mood_service=mood,
        profile_service=profile,
        settings_service=settings,
        enabled=True,
    )
    return db, settings, memory, reply, llm


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def test_openness_defaults_to_neutral(tmp_path) -> None:
    db, settings, *_ = _build_services(tmp_path)
    with db:
        assert settings.get_openness(1) == DEFAULT_OPENNESS == "neutral"


def test_per_contact_overrides_global(tmp_path) -> None:
    db, settings, *_ = _build_services(tmp_path)
    with db:
        settings.set_bot_setting(OPENNESS_SETTING, "open")
        assert settings.get_openness(1) == "open"  # global
        settings.set_openness(1, "reserved")
        assert settings.get_openness(1) == "reserved"  # per-contact wins


def test_set_openness_validates(tmp_path) -> None:
    db, settings, *_ = _build_services(tmp_path)
    with db:
        with pytest.raises(ValueError, match="openness"):
            settings.set_openness(1, "bogus")


def test_directive_changes_with_level() -> None:
    assert _openness_directive("open", "ru") != _openness_directive("reserved", "ru")
    assert "сдержан" in _openness_directive("reserved", "ru").lower()
    assert "guarded" in _openness_directive("reserved", "en").lower()


# ---------------------------------------------------------------------------
# Prompt injection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_openness_directive_injected_into_system_prompt(tmp_path) -> None:
    db, settings, memory, reply, llm = _build_services(tmp_path)
    with db:
        settings.set_openness(1, "reserved")
        await reply.generate_reply(1, "привет")
        system = llm.complete.await_args.args[0][0]["content"]
        assert "сдержанно" in system


@pytest.mark.asyncio
async def test_style_not_applied_when_reserved(tmp_path) -> None:
    db, settings, memory, reply, llm = _build_services(tmp_path)
    with db:
        memory.set_style_profile(1, "пишет коротко, со смайлами", covered_count=5)
        settings.set_style_learning(1, True)
        settings.set_openness(1, "reserved")
        await reply.generate_reply(1, "привет")
        system = llm.complete.await_args.args[0][0]["content"]
        assert "пишет коротко" not in system  # style suppressed by reserved


@pytest.mark.asyncio
async def test_style_applied_when_open_and_enabled(tmp_path) -> None:
    db, settings, memory, reply, llm = _build_services(tmp_path)
    with db:
        memory.set_style_profile(1, "пишет коротко, со смайлами", covered_count=5)
        settings.set_style_learning(1, True)
        settings.set_openness(1, "open")
        await reply.generate_reply(1, "привет")
        system = llm.complete.await_args.args[0][0]["content"]
        assert "пишет коротко" in system


@pytest.mark.asyncio
async def test_style_uses_only_the_current_contact(tmp_path) -> None:
    db, settings, memory, reply, llm = _build_services(tmp_path)
    with db:
        current = settings.get_user_settings(1)
        settings.save_user_settings(
            replace(current, style_learning_enabled=True, persona_preset="friend")
        )
        memory.set_owner_style_profile("global", "общий стиль", covered_through_message_id=3)
        memory.set_owner_style_profile(
            "persona:friend", "стиль друзей", covered_through_message_id=4
        )
        memory.set_style_profile(1, "личная деталь", covered_count=5)
        settings.set_openness(1, "open")

        await reply.generate_reply(1, "привет")

        system = llm.complete.await_args.args[0][0]["content"]
        assert "общий стиль" not in system
        assert "стиль друзей" not in system
        assert "личная деталь" in system


@pytest.mark.asyncio
async def test_style_not_applied_when_learning_disabled(tmp_path) -> None:
    db, settings, memory, reply, llm = _build_services(tmp_path)
    with db:
        memory.set_style_profile(1, "пишет коротко, со смайлами", covered_count=5)
        # style_learning_enabled defaults to False
        settings.set_openness(1, "open")
        await reply.generate_reply(1, "привет")
        system = llm.complete.await_args.args[0][0]["content"]
        assert "пишет коротко" not in system
