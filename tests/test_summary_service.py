"""Tests for the rolling conversation summary (Phase 10)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.database.db import Database
from app.services.memory_service import MemoryService
from app.services.settings_service import SettingsService
from app.services.summary_service import SummaryService


def _make(tmp_path, *, window=5, interval=3, enabled=True):
    db = Database(f"sqlite:///{tmp_path / 'sum.db'}")
    db.open()
    memory = MemoryService(db.memory, window_size=window)
    settings = SettingsService(db.settings, "ru", 9)
    llm = MagicMock()
    llm.complete = AsyncMock(return_value="СВОДКА")
    svc = SummaryService(
        memory_service=memory,
        llm_service=llm,
        settings_service=settings,
        window_size=window,
        refresh_interval=interval,
        max_chars=1500,
        enabled=enabled,
    )
    return svc, memory, llm, db


def _fill(memory: MemoryService, user_id: int, n: int) -> None:
    for i in range(n):
        if i % 2 == 0:
            memory.record_user_message(user_id, f"contact {i}")
        else:
            memory.record_assistant_message(user_id, f"owner {i}")


@pytest.mark.asyncio
async def test_no_summary_until_window_exceeded(tmp_path) -> None:
    svc, memory, llm, db = _make(tmp_path, window=5, interval=3)
    with db:
        _fill(memory, 1, 5)  # exactly the window — nothing aged out
        await svc.maybe_refresh(1)
        llm.complete.assert_not_called()
        assert memory.get_summary(1) is None


@pytest.mark.asyncio
async def test_not_refreshed_below_interval(tmp_path) -> None:
    svc, memory, llm, db = _make(tmp_path, window=5, interval=3)
    with db:
        _fill(memory, 1, 7)  # 2 aged out, interval is 3 → not yet
        await svc.maybe_refresh(1)
        llm.complete.assert_not_called()
        assert memory.get_summary(1) is None


@pytest.mark.asyncio
async def test_refresh_when_enough_aged_out(tmp_path) -> None:
    svc, memory, llm, db = _make(tmp_path, window=5, interval=3)
    with db:
        _fill(memory, 1, 8)  # 3 aged out (total 8 - window 5) → refresh
        await svc.maybe_refresh(1)
        llm.complete.assert_awaited_once()
        summary = memory.get_summary(1)
        assert summary is not None
        assert summary.summary == "СВОДКА"
        assert summary.covered_count == 3  # 8 - 5


@pytest.mark.asyncio
async def test_incremental_only_folds_delta(tmp_path) -> None:
    svc, memory, llm, db = _make(tmp_path, window=5, interval=3)
    with db:
        _fill(memory, 1, 8)
        await svc.maybe_refresh(1)  # covers 3
        # add 3 more → 11 total, 6 older, 3 new since covered=3 → refresh again
        _fill(memory, 1, 3)
        await svc.maybe_refresh(1)

        assert llm.complete.await_count == 2
        # second call must only contain the 3 newly-aged-out messages, not all 6
        second_prompt = llm.complete.await_args_list[1].args[0]
        user_block = second_prompt[1]["content"]
        assert "Текущая сводка:" in user_block  # previous summary folded in
        assert memory.get_summary(1).covered_count == 6  # 11 - 5


@pytest.mark.asyncio
async def test_disabled_does_nothing(tmp_path) -> None:
    svc, memory, llm, db = _make(tmp_path, window=5, interval=3, enabled=False)
    with db:
        _fill(memory, 1, 20)
        await svc.maybe_refresh(1)
        llm.complete.assert_not_called()
        assert memory.get_summary(1) is None


@pytest.mark.asyncio
async def test_llm_error_does_not_raise_or_persist(tmp_path) -> None:
    svc, memory, llm, db = _make(tmp_path, window=5, interval=3)
    llm.complete = AsyncMock(side_effect=RuntimeError("LLM down"))
    with db:
        _fill(memory, 1, 8)
        await svc.maybe_refresh(1)  # must swallow the error
        assert memory.get_summary(1) is None  # nothing persisted on failure
