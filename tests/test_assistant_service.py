"""Tests for the owner personal-assistant mode."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.database.db import Database
from app.services.assistant_service import AssistantService
from app.services.memory_service import MemoryService
from app.services.settings_service import SettingsService

OWNER = 100000001


def _make(tmp_path, *, reply_text="ну привет!"):
    db = Database(f"sqlite:///{tmp_path / 'assistant.db'}")
    db.open()
    memory = MemoryService(db.memory, window_size=20)
    settings = SettingsService(db.settings, default_language="ru", default_greeting_hour=9)
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=reply_text)
    svc = AssistantService(
        repository=db.assistant_profiles,
        memory_service=memory,
        llm_service=llm,
        settings_service=settings,
        enabled=True,
    )
    return svc, memory, llm, db


# ── Profiles ────────────────────────────────────────────────────────────────────


def test_create_and_list(tmp_path) -> None:
    svc, _, _, db = _make(tmp_path)
    with db:
        svc.create_or_update(OWNER, "english", "Ты учитель английского")
        svc.create_or_update(OWNER, "brainstorm", "Ты партнёр по брейнсторму")
        names = [p.name for p in svc.list_profiles(OWNER)]
        assert names == ["english", "brainstorm"]


def test_create_updates_existing_persona(tmp_path) -> None:
    svc, _, _, db = _make(tmp_path)
    with db:
        svc.create_or_update(OWNER, "english", "v1")
        svc.create_or_update(OWNER, "english", "v2")
        profiles = svc.list_profiles(OWNER)
        assert len(profiles) == 1
        assert profiles[0].persona == "v2"


def test_name_validation(tmp_path) -> None:
    svc, _, _, db = _make(tmp_path)
    with db:
        with pytest.raises(ValueError, match="Имя профиля"):
            svc.create_or_update(OWNER, "a" * 31, "persona")


def test_persona_required(tmp_path) -> None:
    svc, _, _, db = _make(tmp_path)
    with db:
        with pytest.raises(ValueError, match="персону"):
            svc.create_or_update(OWNER, "english", "   ")


def test_profiles_isolated_per_owner(tmp_path) -> None:
    svc, _, _, db = _make(tmp_path)
    with db:
        svc.create_or_update(OWNER, "english", "p")
        assert svc.list_profiles(999) == []


# ── Active state ────────────────────────────────────────────────────────────────


def test_not_active_by_default(tmp_path) -> None:
    svc, _, _, db = _make(tmp_path)
    with db:
        svc.create_or_update(OWNER, "english", "p")
        assert svc.is_active(OWNER) is False
        assert svc.active_profile(OWNER) is None


def test_activate_and_off(tmp_path) -> None:
    svc, _, _, db = _make(tmp_path)
    with db:
        p = svc.create_or_update(OWNER, "english", "p")
        svc.set_active(OWNER, p.id)
        assert svc.is_active(OWNER) is True
        assert svc.active_profile(OWNER).name == "english"
        svc.set_active(OWNER, None)
        assert svc.is_active(OWNER) is False


def test_activate_by_name(tmp_path) -> None:
    svc, _, _, db = _make(tmp_path)
    with db:
        svc.create_or_update(OWNER, "english", "p")
        assert svc.activate_by_name(OWNER, "english").name == "english"
        assert svc.is_active(OWNER) is True
        assert svc.activate_by_name(OWNER, "missing") is None


def test_disabled_service_never_active(tmp_path) -> None:
    svc, _, _, db = _make(tmp_path)
    with db:
        p = svc.create_or_update(OWNER, "english", "p")
        svc.set_active(OWNER, p.id)
        svc.enabled = False
        assert svc.is_active(OWNER) is False


# ── Memory key isolation ────────────────────────────────────────────────────────


def test_memory_key_is_negative() -> None:
    assert AssistantService.memory_key(1) < 0
    assert AssistantService.memory_key(1) != AssistantService.memory_key(2)


# ── Reply ───────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reply_uses_persona_and_isolated_memory(tmp_path) -> None:
    svc, memory, llm, db = _make(tmp_path, reply_text="hello there")
    with db:
        p = svc.create_or_update(OWNER, "english", "You are an English teacher")
        svc.set_active(OWNER, p.id)

        reply = await svc.reply(OWNER, "привет")
        assert reply == "hello there"

        # The system prompt sent to the LLM is the profile persona
        sent = llm.complete.await_args.args[0]
        assert sent[0] == {"role": "system", "content": "You are an English teacher"}
        assert sent[-1] == {"role": "user", "content": "привет"}

        # The exchange is stored under the isolated negative key, NOT under OWNER
        key = AssistantService.memory_key(p.id)
        assert memory.count_messages(key) == 2
        assert memory.count_messages(OWNER) == 0


@pytest.mark.asyncio
async def test_reply_persists_history_across_turns(tmp_path) -> None:
    svc, memory, llm, db = _make(tmp_path)
    with db:
        p = svc.create_or_update(OWNER, "english", "persona")
        svc.set_active(OWNER, p.id)

        await svc.reply(OWNER, "первое")
        await svc.reply(OWNER, "второе")

        # Second call should have seen the first exchange in history.
        second_sent = llm.complete.await_args.args[0]
        contents = [m["content"] for m in second_sent]
        assert "первое" in contents  # prior user turn present
        key = AssistantService.memory_key(p.id)
        assert memory.count_messages(key) == 4  # 2 turns × (user+assistant)


@pytest.mark.asyncio
async def test_reply_none_when_inactive(tmp_path) -> None:
    svc, _, llm, db = _make(tmp_path)
    with db:
        svc.create_or_update(OWNER, "english", "p")  # exists but not active
        assert await svc.reply(OWNER, "привет") is None
        llm.complete.assert_not_called()


# ── Reset / delete ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reset_history(tmp_path) -> None:
    svc, memory, _, db = _make(tmp_path)
    with db:
        p = svc.create_or_update(OWNER, "english", "p")
        svc.set_active(OWNER, p.id)
        await svc.reply(OWNER, "привет")
        assert memory.count_messages(AssistantService.memory_key(p.id)) == 2
        assert svc.reset_history(OWNER) is True
        assert memory.count_messages(AssistantService.memory_key(p.id)) == 0


@pytest.mark.asyncio
async def test_delete_active_profile_turns_off_and_clears(tmp_path) -> None:
    svc, memory, _, db = _make(tmp_path)
    with db:
        p = svc.create_or_update(OWNER, "english", "p")
        svc.set_active(OWNER, p.id)
        await svc.reply(OWNER, "привет")
        key = AssistantService.memory_key(p.id)
        assert memory.count_messages(key) == 2

        assert svc.delete(OWNER, "english") is True
        assert svc.is_active(OWNER) is False
        assert memory.count_messages(key) == 0
        assert svc.list_profiles(OWNER) == []


def test_delete_missing_returns_false(tmp_path) -> None:
    svc, _, _, db = _make(tmp_path)
    with db:
        assert svc.delete(OWNER, "nope") is False
