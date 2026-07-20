"""Tests for per-contact durable facts extraction (Phase 11)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.database.db import Database
from app.services.contact_facts_service import (
    KNOWN_KEYS,
    ContactFactsService,
    _build_extraction_messages,
    _parse_facts_json,
)
from app.services.memory_service import MemoryService
from app.services.settings_service import SettingsService

OWNER_ID = 100000001
_ALLOWED = frozenset(KNOWN_KEYS)


def _make(tmp_path, *, interval=5, enabled=True, llm_return=None):
    db = Database(f"sqlite:///{tmp_path / 'facts.db'}")
    db.open()
    memory = MemoryService(db.memory, window_size=10)
    settings = SettingsService(db.settings, "ru", 9)
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=json.dumps(llm_return or {}, ensure_ascii=False))
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
    result = _parse_facts_json(raw, _ALLOWED)
    assert result == {"name": "Саша", "city": "Москва"}


def test_parse_fenced_json() -> None:
    raw = '```json\n{"name": "Ivan", "occupation": "дизайнер"}\n```'
    result = _parse_facts_json(raw, _ALLOWED)
    assert result == {"name": "Ivan", "occupation": "дизайнер"}


def test_parse_ignores_unknown_keys() -> None:
    raw = '{"name": "Петя", "secret_key": "oops", "city": "Минск"}'
    result = _parse_facts_json(raw, _ALLOWED)
    assert "secret_key" not in result
    assert result["name"] == "Петя"
    assert result["city"] == "Минск"


def test_parse_ignores_empty_values() -> None:
    raw = '{"name": "Ира", "city": ""}'
    result = _parse_facts_json(raw, _ALLOWED)
    assert "city" not in result


def test_parse_invalid_returns_empty() -> None:
    assert _parse_facts_json("not json at all", _ALLOWED) == {}
    assert _parse_facts_json("{}", _ALLOWED) == {}
    assert _parse_facts_json("[]", _ALLOWED) == {}


def test_extraction_prompt_rejects_role_leakage_and_chat_noise() -> None:
    prompt = _build_extraction_messages(
        [
            {"role": "assistant", "content": "У меня есть сын Лёша"},
            {"role": "user", "content": "А у меня нет детей"},
            {"role": "user", "content": "Люблю иногда пошутить про мухоморы"},
        ],
        {"family": "сын Лёша"},
        "ru",
        multi_keys={"family", "interests"},
    )

    system = prompt[0]["content"]
    user = prompt[1]["content"]
    assert "никогда не приписывай Контакту факты из сообщений Я" in system
    assert "шутки, сарказм, вопросы" in system
    assert "не повторяй их без нового явного подтверждения" in system
    assert "Я: У меня есть сын Лёша" in user
    assert "Контакт: А у меня нет детей" in user


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
    svc, memory, llm, db = _make(tmp_path, interval=5, llm_return={"name": "Дима", "city": "Брест"})
    with db:
        _fill(memory, 1, 5)  # exactly 5 → extract
        await svc.maybe_extract(1)
        llm.complete.assert_awaited_once()
        facts = svc.facts_as_dict(1)
        assert facts["name"] == "Дима"
        assert facts["city"] == "Брест"


@pytest.mark.asyncio
async def test_extraction_not_repeated_until_more_messages(tmp_path) -> None:
    svc, memory, llm, db = _make(tmp_path, interval=5, llm_return={"name": "Аня"})
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


# ---------------------------------------------------------------------------
# Multi-valued facts
# ---------------------------------------------------------------------------


def test_multi_builtin_appends(tmp_path) -> None:
    """interests is a built-in multi key — set_fact appends, not overwrites."""
    svc, memory, llm, db = _make(tmp_path)
    with db:
        svc.set_fact(1, "interests", "футбол")
        svc.set_fact(1, "interests", "музыка")
        structured = svc.facts_structured(1)
        assert structured["interests"]["multi"] is True
        assert structured["interests"]["values"] == ["футбол", "музыка"]


def test_multi_dedup_case_insensitive(tmp_path) -> None:
    svc, memory, llm, db = _make(tmp_path)
    with db:
        svc.set_fact(1, "interests", "Футбол")
        svc.set_fact(1, "interests", "футбол")
        assert svc.facts_structured(1)["interests"]["values"] == ["Футбол"]


def test_multi_comma_split(tmp_path) -> None:
    svc, memory, llm, db = _make(tmp_path)
    with db:
        svc.set_fact(1, "interests", "футбол, музыка, кино")
        assert svc.facts_structured(1)["interests"]["values"] == ["футбол", "музыка", "кино"]


def test_facts_as_dict_joins_multi(tmp_path) -> None:
    svc, memory, llm, db = _make(tmp_path)
    with db:
        svc.set_fact(1, "interests", "футбол")
        svc.set_fact(1, "interests", "музыка")
        svc.set_fact(1, "name", "Катя")
        flat = svc.facts_as_dict(1)
        assert flat["interests"] == "футбол, музыка"
        assert flat["name"] == "Катя"


def test_facts_structured_single(tmp_path) -> None:
    svc, memory, llm, db = _make(tmp_path)
    with db:
        svc.set_fact(1, "name", "Катя")
        s = svc.facts_structured(1)
        assert s["name"]["multi"] is False
        assert s["name"]["values"] == ["Катя"]
        assert s["name"]["label"] == "Имя"  # localized built-in label


def test_remove_fact_value(tmp_path) -> None:
    svc, memory, llm, db = _make(tmp_path)
    with db:
        svc.set_fact(1, "interests", "футбол, музыка, кино")
        svc.remove_fact_value(1, "interests", "музыка")
        assert svc.facts_structured(1)["interests"]["values"] == ["футбол", "кино"]


def test_remove_last_value_deletes_key(tmp_path) -> None:
    svc, memory, llm, db = _make(tmp_path)
    with db:
        svc.set_fact(1, "interests", "футбол")
        svc.remove_fact_value(1, "interests", "футбол")
        assert "interests" not in svc.facts_structured(1)


def test_multi_value_cap(tmp_path) -> None:
    from app.services.contact_facts_service import MAX_FACT_VALUES

    svc, memory, llm, db = _make(tmp_path)
    with db:
        for i in range(MAX_FACT_VALUES + 5):
            svc.set_fact(1, "interests", f"item{i}")
        assert len(svc.facts_structured(1)["interests"]["values"]) == MAX_FACT_VALUES


def test_custom_multi_category(tmp_path) -> None:
    from app.services.fact_categories_service import FactCategoriesService

    db = Database(f"sqlite:///{tmp_path / 'facts.db'}")
    db.open()
    with db:
        cats = FactCategoriesService(db.fact_categories)
        fav_key = cats.add_category("Любимое", multi=True)
        memory = MemoryService(db.memory, window_size=10)
        settings = SettingsService(db.settings, "ru", 9)
        svc = ContactFactsService(
            repository=db.facts,
            memory_service=memory,
            llm_service=MagicMock(),
            settings_service=settings,
            refresh_interval=5,
            enabled=True,
            categories_service=cats,
        )
        svc.set_fact(1, fav_key, "суши")
        svc.set_fact(1, fav_key, "Матрица")
        assert svc.facts_structured(1)[fav_key]["values"] == ["суши", "Матрица"]


def test_facts_for_prompt_uses_labels(tmp_path) -> None:
    """The reply prompt must see human labels, not raw slugs."""
    from app.services.fact_categories_service import FactCategoriesService

    db = Database(f"sqlite:///{tmp_path / 'facts.db'}")
    db.open()
    with db:
        cats = FactCategoriesService(db.fact_categories)
        fav_key = cats.add_category("Любимая еда", multi=True)
        dislike_key = cats.add_category("Не нравится", multi=True)
        memory = MemoryService(db.memory, window_size=10)
        settings = SettingsService(db.settings, "ru", 9)
        svc = ContactFactsService(
            repository=db.facts,
            memory_service=memory,
            llm_service=MagicMock(),
            settings_service=settings,
            refresh_interval=5,
            enabled=True,
            categories_service=cats,
        )
        svc.set_fact(1, "name", "Ирина")
        svc.set_fact(1, fav_key, "безе")
        svc.set_fact(1, dislike_key, "шоколадный торт, клубнику со сметаной")

        prompt_facts = svc.facts_for_prompt(1, "ru")
        # Built-in localized + custom labels, no raw slugs
        assert prompt_facts["Имя"] == "Ирина"
        assert prompt_facts["Любимая еда"] == "безе"
        assert prompt_facts["Не нравится"] == "шоколадный торт, клубнику со сметаной"
        assert fav_key not in prompt_facts
        assert dislike_key not in prompt_facts


@pytest.mark.asyncio
async def test_extraction_appends_multi(tmp_path) -> None:
    """Across extractions, a multi key accumulates rather than overwrites."""
    db = Database(f"sqlite:///{tmp_path / 'facts.db'}")
    db.open()
    memory = MemoryService(db.memory, window_size=10)
    settings = SettingsService(db.settings, "ru", 9)

    call_count = 0
    returns = [{"interests": "футбол"}, {"interests": "музыка"}]

    async def _complete(messages):
        nonlocal call_count
        r = returns[min(call_count, len(returns) - 1)]
        call_count += 1
        return json.dumps(r, ensure_ascii=False)

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
        _fill(memory, 1, 3)
        await svc.maybe_extract(1)
        assert svc.facts_structured(1)["interests"]["values"] == ["футбол", "музыка"]


def test_clear_facts_resets_extraction_watermark(tmp_path) -> None:
    svc, memory, llm, db = _make(tmp_path)
    with db:
        svc.set_fact(1, "name", "Ошибочное имя")
        db.facts.set_meta(1, 100)

        svc.clear_facts(1)

        assert svc.facts_as_dict(1) == {}
        assert db.facts.get_meta(1) is None


@pytest.mark.asyncio
async def test_rebuild_reextracts_full_history_in_batches(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.services.contact_facts_service.REBUILD_BATCH_SIZE", 3)
    svc, memory, llm, db = _make(tmp_path, interval=2)
    llm.complete = AsyncMock(
        side_effect=[
            '{"name": "Ирина"}',
            '{"city": "Минск"}',
            '{"interests": "прогулки"}',
        ]
    )
    with db:
        _fill(memory, 1, 8)
        svc.set_fact(1, "name", "Имя неизвестно")
        db.facts.set_meta(1, 8)

        result = await svc.rebuild(1)

        assert llm.complete.await_count == 3
        assert result == {
            "name": "Ирина",
            "city": "Минск",
            "interests": "прогулки",
        }
        assert memory.count_messages(1) == 8
        assert db.facts.get_meta(1).last_message_count == 8
