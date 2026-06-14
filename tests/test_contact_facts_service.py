"""Tests for per-contact durable facts extraction (Phase 11)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.database.db import Database
from app.services.contact_facts_service import (
    ContactFactsService,
    _parse_facts_json,
)
from app.services.memory_service import MemoryService
from app.services.settings_service import SettingsService

OWNER_ID = 100000001


def _make(tmp_path, *, interval=5, enabled=True, llm_return=None):
    db = Database(f"sqlite:///{tmp_path / 'facts.db'}")
    db.open()
    memory = MemoryService(db.memory, window_size=10)
    settings = SettingsService(db.settings, "ru", 9)
    llm = MagicMock()
    llm.complete = AsyncMock(
        return_value=json.dumps(llm_return or {}, ensure_ascii=False)
    )
    svc = ContactFactsService(
        repository=db.facts,
        memory_service=memory,
        llm_service=llm,
        settings_service=settings,
        refresh_interval=interval,
        enabled=enabled,
    )
    return svc, memory, llm, db


def _fill(memory: MemoryService, user_id: int, n: int) -> None:
    for i in range(n):
        if i % 2 == 0:
            memory.record_user_message(user_id, f"contact msg {i}")
        else:
            memory.record_assistant_message(user_id, f"owner msg {i}")


# ---------------------------------------------------------------------------
# _parse_facts_json unit tests
# ---------------------------------------------------------------------------


def test_parse_plain_json() -> None:
    raw = '{"name": "Саша", "city": "Москва"}'
    result = _parse_facts_json(raw)
    assert result == {"name": "Саша", "city": "Москва"}


def test_parse_fenced_json() -> None:
    raw = "```json\n{\"name\": \"Ivan\", \"occupation\": \"дизайнер\"}\n```"
    result = _parse_facts_json(raw)
    assert result == {"name": "Ivan", "occupation": "дизайнер"}


def test_parse_ignores_unknown_keys() -> None:
    raw = '{"name": "Петя", "secret_key": "oops", "city": "Минск"}'
    result = _parse_facts_json(raw)
    assert "secret_key" not in result
    assert result["name"] == "Петя"
    assert result["city"] == "Минск"


def test_parse_ignores_empty_values() -> None:
    raw = '{"name": "Ира", "city": ""}'
    result = _parse_facts_json(raw)
    assert "city" not in result


def test_parse_invalid_returns_empty() -> None:
    assert _parse_facts_json("not json at all") == {}
    assert _parse_facts_json("{}") == {}
    assert _parse_facts_json("[]") == {}


# ---------------------------------------------------------------------------
# Service integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_extraction_below_interval(tmp_path) -> None:
    svc, memory, llm, db = _make(tmp_path, interval=5)
    with db:
        _fill(memory, 1, 4)  # 4 messages, interval=5 → skip
        await svc.maybe_extract(1)
        llm.complete.assert_not_called()
        assert svc.facts_as_dict(1) == {}


@pytest.mark.asyncio
async def test_extraction_fires_at_interval(tmp_path) -> None:
    svc, memory, llm, db = _make(
        tmp_path, interval=5, llm_return={"name": "Дима", "city": "Брест"}
    )
    with db:
        _fill(memory, 1, 5)  # exactly 5 → extract
        await svc.maybe_extract(1)
        llm.complete.assert_awaited_once()
        facts = svc.facts_as_dict(1)
        assert facts["name"] == "Дима"
        assert facts["city"] == "Брест"


@pytest.mark.asyncio
async def test_extraction_not_repeated_until_more_messages(tmp_path) -> None:
    svc, memory, llm, db = _make(
        tmp_path, interval=5, llm_return={"name": "Аня"}
    )
    with db:
        _fill(memory, 1, 5)
        await svc.maybe_extract(1)
        assert llm.complete.await_count == 1

        # call again without adding messages → should not re-extract
        await svc.maybe_extract(1)
        assert llm.complete.await_count == 1


@pytest.mark.asyncio
async def test_extraction_reruns_after_more_messages(tmp_path) -> None:
    svc, memory, llm, db = _make(
        tmp_path, interval=5, llm_return={"name": "Коля", "city": "Гомель"}
    )
    with db:
        _fill(memory, 1, 5)
        await svc.maybe_extract(1)
        assert llm.complete.await_count == 1

        # add 5 more
        _fill(memory, 1, 5)
        await svc.maybe_extract(1)
        assert llm.complete.await_count == 2


@pytest.mark.asyncio
async def test_facts_merged_not_replaced(tmp_path) -> None:
    """Existing facts survive across extractions; new run adds/updates."""
    db = Database(f"sqlite:///{tmp_path / 'facts.db'}")
    db.open()
    memory = MemoryService(db.memory, window_size=10)
    settings = SettingsService(db.settings, "ru", 9)

    call_count = 0
    returns = [
        {"name": "Света", "city": "Минск"},
        {"city": "Москва", "occupation": "юрист"},  # city updated, name not mentioned
    ]

    async def _complete(messages):
        nonlocal call_count
        r = returns[min(call_count, len(returns) - 1)]
        call_count += 1
        return json.dumps(r)

    llm = MagicMock()
    llm.complete = _complete

    svc = ContactFactsService(
        repository=db.facts,
        memory_service=memory,
        llm_service=llm,
        settings_service=settings,
        refresh_interval=3,
        enabled=True,
    )
    with db:
        _fill(memory, 1, 3)
        await svc.maybe_extract(1)
        assert svc.facts_as_dict(1)["name"] == "Света"
        assert svc.facts_as_dict(1)["city"] == "Минск"

        _fill(memory, 1, 3)
        await svc.maybe_extract(1)
        facts = svc.facts_as_dict(1)
        # name persists from first extraction
        assert facts["name"] == "Света"
        # city updated
        assert facts["city"] == "Москва"
        # new fact added
        assert facts["occupation"] == "юрист"


@pytest.mark.asyncio
async def test_disabled_does_nothing(tmp_path) -> None:
    svc, memory, llm, db = _make(tmp_path, enabled=False)
    with db:
        _fill(memory, 1, 20)
        await svc.maybe_extract(1)
        llm.complete.assert_not_called()
        assert svc.facts_as_dict(1) == {}


@pytest.mark.asyncio
async def test_llm_error_does_not_raise(tmp_path) -> None:
    svc, memory, llm, db = _make(tmp_path, interval=5)
    llm.complete = AsyncMock(side_effect=RuntimeError("LLM down"))
    with db:
        _fill(memory, 1, 5)
        await svc.maybe_extract(1)  # must not raise
        assert svc.facts_as_dict(1) == {}


def test_set_fact_validates_key(tmp_path) -> None:
    svc, memory, llm, db = _make(tmp_path)
    with db:
        with pytest.raises(ValueError, match="Unknown fact key"):
            svc.set_fact(1, "unknown_bad_key", "value")


def test_manual_set_and_delete(tmp_path) -> None:
    svc, memory, llm, db = _make(tmp_path)
    with db:
        svc.set_fact(1, "name", "Вася")
        svc.set_fact(1, "city", "Гродно")
        assert svc.facts_as_dict(1) == {"name": "Вася", "city": "Гродно"}
        svc.delete_fact(1, "city")
        assert svc.facts_as_dict(1) == {"name": "Вася"}
        svc.clear_facts(1)
        assert svc.facts_as_dict(1) == {}
