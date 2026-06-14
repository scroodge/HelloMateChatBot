"""Tests for owner writing-style learning (Phase 12)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.database.db import Database
from app.services.memory_service import MemoryService
from app.services.settings_service import SettingsService
from app.services.style_service import StyleService


def _make(tmp_path, *, interval=3, enabled=True, profile_return="СТИЛЬ"):
    db = Database(f"sqlite:///{tmp_path / 'style.db'}")
    db.open()
    memory = MemoryService(db.memory, window_size=20)
    settings = SettingsService(db.settings, "ru", 9)
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=profile_return)
    svc = StyleService(
        memory_service=memory,
        llm_service=llm,
        settings_service=settings,
        refresh_interval=interval,
        max_chars=800,
        enabled=enabled,
    )
    return svc, memory, settings, llm, db


def _enable_style(settings: SettingsService, user_id: int) -> None:
    settings.set_style_learning(user_id, True)


def _fill_owner(memory: MemoryService, user_id: int, n: int) -> None:
    for i in range(n):
        memory.record_assistant_message(user_id, f"owner reply {i}", authored_by="owner")


@pytest.mark.asyncio
async def test_no_refresh_when_style_learning_disabled(tmp_path) -> None:
    svc, memory, settings, llm, db = _make(tmp_path, interval=3)
    with db:
        _fill_owner(memory, 1, 10)  # plenty of owner messages
        await svc.maybe_refresh(1)  # but opt-in is OFF
        llm.complete.assert_not_called()
        assert memory.get_style_profile(1) is None


@pytest.mark.asyncio
async def test_no_refresh_below_interval(tmp_path) -> None:
    svc, memory, settings, llm, db = _make(tmp_path, interval=3)
    with db:
        _enable_style(settings, 1)
        _fill_owner(memory, 1, 2)  # 2 < interval 3
        await svc.maybe_refresh(1)
        llm.complete.assert_not_called()
        assert memory.get_style_profile(1) is None


@pytest.mark.asyncio
async def test_refresh_when_enough_owner_messages(tmp_path) -> None:
    svc, memory, settings, llm, db = _make(tmp_path, interval=3)
    with db:
        _enable_style(settings, 1)
        _fill_owner(memory, 1, 3)
        await svc.maybe_refresh(1)
        llm.complete.assert_awaited_once()
        profile = memory.get_style_profile(1)
        assert profile is not None
        assert profile.profile == "СТИЛЬ"
        assert profile.covered_count == 3


@pytest.mark.asyncio
async def test_only_owner_messages_counted(tmp_path) -> None:
    """Bot-authored and contact messages must not feed the style profile."""
    svc, memory, settings, llm, db = _make(tmp_path, interval=3)
    with db:
        _enable_style(settings, 1)
        # mix in bot replies and contact messages — these should be ignored
        memory.record_user_message(1, "contact hi")
        memory.record_assistant_message(1, "bot reply", authored_by="bot")
        memory.record_assistant_message(1, "bot reply 2", authored_by="bot")
        _fill_owner(memory, 1, 2)  # only 2 owner messages < interval 3
        await svc.maybe_refresh(1)
        llm.complete.assert_not_called()  # not enough OWNER messages despite 5 total


@pytest.mark.asyncio
async def test_incremental_only_folds_new_owner_messages(tmp_path) -> None:
    svc, memory, settings, llm, db = _make(tmp_path, interval=3)
    with db:
        _enable_style(settings, 1)
        _fill_owner(memory, 1, 3)
        await svc.maybe_refresh(1)
        assert llm.complete.await_count == 1

        _fill_owner(memory, 1, 3)  # 3 more owner messages
        await svc.maybe_refresh(1)
        assert llm.complete.await_count == 2

        second_prompt = llm.complete.await_args_list[1].args[0]
        user_block = second_prompt[1]["content"]
        assert "Текущее описание стиля:" in user_block  # prior profile folded in
        assert memory.get_style_profile(1).covered_count == 6


@pytest.mark.asyncio
async def test_disabled_service_does_nothing(tmp_path) -> None:
    svc, memory, settings, llm, db = _make(tmp_path, interval=3, enabled=False)
    with db:
        _enable_style(settings, 1)
        _fill_owner(memory, 1, 10)
        await svc.maybe_refresh(1)
        llm.complete.assert_not_called()


@pytest.mark.asyncio
async def test_llm_error_does_not_persist(tmp_path) -> None:
    svc, memory, settings, llm, db = _make(tmp_path, interval=3)
    llm.complete = AsyncMock(side_effect=RuntimeError("down"))
    with db:
        _enable_style(settings, 1)
        _fill_owner(memory, 1, 3)
        await svc.maybe_refresh(1)
        assert memory.get_style_profile(1) is None
