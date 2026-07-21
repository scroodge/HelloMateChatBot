"""Tests for per-contact few-shot examples."""

from __future__ import annotations

import pytest

from app.database.db import Database
from app.services.examples_service import (
    MAX_EXAMPLES,
    PROMPT_EXAMPLES_PER_KIND,
    ContactExamplesService,
)


def _make_service(tmp_path) -> tuple[ContactExamplesService, Database]:
    db = Database(f"sqlite:///{tmp_path / 'examples.db'}")
    db.open()
    return ContactExamplesService(db.examples), db


def test_add_and_list(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        svc.add_example(1, "привет", "о, привет! как ты?")
        svc.add_example(1, "что делаешь?", "да так, отдыхаю")
        items = svc.list_examples(1)
        assert len(items) == 2
        assert items[0].contact_message == "привет"
        assert items[1].reply_text == "да так, отдыхаю"


def test_delete(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        ex = svc.add_example(1, "привет", "здарова")
        svc.add_example(1, "пока", "давай")
        svc.delete_example(1, ex.id)
        items = svc.list_examples(1)
        assert len(items) == 1
        assert items[0].contact_message == "пока"


def test_clear(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        svc.add_example(1, "a", "b")
        svc.add_example(1, "c", "d")
        svc.clear_examples(1)
        assert svc.list_examples(1) == []


def test_empty_fields_rejected(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        with pytest.raises(ValueError):
            svc.add_example(1, "   ", "ответ")
        with pytest.raises(ValueError):
            svc.add_example(1, "сообщение", "")


def test_max_examples_enforced(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        for i in range(MAX_EXAMPLES):
            svc.add_example(1, f"msg {i}", f"reply {i}")
        with pytest.raises(ValueError, match="At most"):
            svc.add_example(1, "one too many", "nope")


def test_fields_truncated(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        ex = svc.add_example(1, "x" * 5000, "y" * 5000)
        assert len(ex.contact_message) == 600
        assert len(ex.reply_text) == 600


def test_examples_isolated_per_contact(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        svc.add_example(1, "a", "b")
        assert svc.list_examples(2) == []


def test_examples_block_empty_when_none(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        assert svc.examples_block(1, "ru") == ""


def test_examples_block_ru(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        svc.add_example(1, "привет", "о, привет!")
        block = svc.examples_block(1, "ru")
        assert "Примеры идеальных ответов" in block
        assert "Контакт: «привет»" in block
        assert "Ответ: «о, привет!»" in block


def test_examples_block_en(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        svc.add_example(1, "hi", "hey there")
        block = svc.examples_block(1, "en")
        assert "Examples of ideal replies" in block
        assert "Contact: «hi»" in block


def test_examples_block_disabled(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        svc.add_example(1, "hi", "hey")
        svc.enabled = False
        assert svc.examples_block(1, "ru") == ""


def test_examples_block_selects_the_closest_examples_for_a_query(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        for message in ["погода минск", "погода брест", "фильм", "работа"]:
            svc.add_example(1, message, f"ответ {message}")

        block = svc.examples_block(1, "ru", query="какая погода в минске?")

        assert "ответ погода минск" in block
        assert "ответ погода брест" in block
        assert "ответ фильм" not in block
        assert block.count("Контакт:") == PROMPT_EXAMPLES_PER_KIND - 1


# ── Negative examples (kind='negative') ────────────────────────────────────────


def test_add_negative_example(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        ex = svc.add_example(1, "привет", "давай позже", kind="negative")
        assert ex.kind == "negative"
        items = svc.list_examples(1)
        assert len(items) == 1
        assert items[0].kind == "negative"


def test_invalid_kind_rejected(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        with pytest.raises(ValueError, match="kind must be"):
            svc.add_example(1, "привет", "ответ", kind="unknown")


def test_caps_are_per_kind(tmp_path) -> None:
    """Positive cap and negative cap are independent — 10+10 allowed."""
    svc, db = _make_service(tmp_path)
    with db:
        for i in range(MAX_EXAMPLES):
            svc.add_example(1, f"pos {i}", f"reply {i}", kind="positive")
        for i in range(MAX_EXAMPLES):
            svc.add_example(1, f"neg {i}", f"bad {i}", kind="negative")
        # Both caps hit — one more of each should fail
        with pytest.raises(ValueError, match="At most"):
            svc.add_example(1, "x", "y", kind="positive")
        with pytest.raises(ValueError, match="At most"):
            svc.add_example(1, "x", "y", kind="negative")


def test_examples_block_negative_only(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        svc.add_example(1, "привет", "да ладно", kind="negative")
        block = svc.examples_block(1, "ru")
        assert "НЕ надо" in block
        assert "Плохой ответ: «да ладно»" in block
        assert "Примеры идеальных" not in block


def test_examples_block_both_kinds_ru(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        svc.add_example(1, "привет", "о, привет!")
        svc.add_example(1, "пока", "давай потом", kind="negative")
        block = svc.examples_block(1, "ru")
        assert "Примеры идеальных ответов" in block
        assert "Ответ: «о, привет!»" in block
        assert "НЕ надо" in block
        assert "Плохой ответ: «давай потом»" in block


def test_examples_block_both_kinds_en(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        svc.add_example(1, "hi", "hey there!")
        svc.add_example(1, "bye", "later maybe", kind="negative")
        block = svc.examples_block(1, "en")
        assert "Examples of ideal replies" in block
        assert "Reply: «hey there!»" in block
        assert "Do NOT reply like this" in block
        assert "Bad reply: «later maybe»" in block


@pytest.mark.asyncio
async def test_examples_injected_into_reply_prompt(tmp_path) -> None:
    """The few-shot block must land in the system prompt of the assembled messages."""
    from unittest.mock import AsyncMock, MagicMock

    from app.services.reply_service import ReplyService

    svc, db = _make_service(tmp_path)
    with db:
        svc.add_example(1, "как дела", "норм, у тебя как?")

        settings = MagicMock()
        settings.get_language = MagicMock(return_value="ru")
        settings.resolve_persona_prompt = MagicMock(return_value="Ты бот")
        settings.get_openness = MagicMock(return_value="neutral")
        settings.get_user_settings = MagicMock(return_value=MagicMock(style_learning_enabled=False))

        memory = MagicMock()
        memory.get_summary = MagicMock(return_value=None)
        memory.as_chat_messages = MagicMock(return_value=[])
        memory.window_size = 20

        profile = MagicMock()
        profile.get_or_create_profile = MagicMock(return_value=MagicMock(display_name=None))

        reply = ReplyService(
            llm_service=MagicMock(complete=AsyncMock(return_value="ответ")),
            memory_service=memory,
            mood_service=MagicMock(latest_mood=MagicMock(return_value=None)),
            profile_service=profile,
            settings_service=settings,
            examples_service=svc,
            enabled=True,
        )

        messages = await reply._build_messages(1, "как дела", "ru")
        system = messages[0]["content"]
        assert "Примеры идеальных ответов" in system
        assert "норм, у тебя как?" in system
