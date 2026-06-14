"""Integration tests exercising the SQLAlchemy repositories against a real DB.

These run on SQLite (file-backed, like production-on-SQLite). Set
``HELLOMATE_TEST_DATABASE_URL`` to a PostgreSQL URL to run the same suite against
Postgres and confirm dialect parity (upserts, RETURNING, booleans, bytea).
"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

import pytest

from app.database.db import Database
from app.models.documents import Document, DocumentChunk
from app.models.greeting_rule import GreetingRule
from app.models.memory import ConversationMessage
from app.models.mood import MoodEntry
from app.models.profile import UserProfile
from app.models.settings import UserSettings


@pytest.fixture()
def database(tmp_path: Path):
    url = os.getenv("HELLOMATE_TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'repo.db'}"
    with Database(url) as db:
        yield db


def _now() -> datetime:
    return datetime.now()


def test_greeting_roundtrip(database: Database) -> None:
    assert database.greetings.get_last_greeting_date(1) is None
    database.greetings.set_last_greeting_date(1, date(2026, 6, 14))
    assert database.greetings.get_last_greeting_date(1) == date(2026, 6, 14)
    database.greetings.set_last_greeting_date(1, date(2026, 6, 15))  # upsert
    assert database.greetings.get_last_greeting_date(1) == date(2026, 6, 15)
    assert database.greetings.list_user_ids() == [1]


def test_settings_upsert_and_booleans(database: Database) -> None:
    saved = database.settings.upsert_user_settings(
        UserSettings(user_id=7, language="en", greeting_enabled=False, use_starters=True)
    )
    assert saved.user_id == 7
    loaded = database.settings.get_user_settings(7)
    assert loaded is not None
    assert loaded.language == "en"
    assert loaded.greeting_enabled is False
    assert loaded.use_starters is True
    # update path
    database.settings.upsert_user_settings(
        UserSettings(user_id=7, language="ru", persona_prompt="be warm")
    )
    reloaded = database.settings.get_user_settings(7)
    assert reloaded is not None
    assert reloaded.language == "ru"
    assert reloaded.persona_prompt == "be warm"


def test_bot_settings(database: Database) -> None:
    database.settings.set_bot_setting("default_persona", "friendly")
    assert database.settings.get_bot_setting("default_persona").value == "friendly"
    database.settings.set_bot_setting("default_persona", "formal")
    assert database.settings.get_bot_setting("default_persona").value == "formal"


def test_profile_roundtrip(database: Database) -> None:
    now = _now()
    database.profiles.upsert_profile(
        UserProfile(
            user_id=3, display_name="Ada", timezone_override=None, created_at=now, last_seen_at=now
        )
    )
    later = _now()
    database.profiles.upsert_profile(
        UserProfile(
            user_id=3,
            display_name="Ada L",
            timezone_override="UTC",
            created_at=now,
            last_seen_at=later,
        )
    )
    loaded = database.profiles.get_profile(3)
    assert loaded is not None
    assert loaded.display_name == "Ada L"
    assert loaded.timezone_override == "UTC"


def test_memory_window_order(database: Database) -> None:
    for i in range(3):
        database.memory.add_message(
            ConversationMessage(id=0, user_id=5, role="user", content=f"m{i}", created_at=_now())
        )
    messages = database.memory.list_messages(5, limit=2)
    assert [m.content for m in messages] == ["m1", "m2"]  # oldest-first within the window


def test_mood_roundtrip(database: Database) -> None:
    entry = database.moods.add_mood_entry(
        MoodEntry(id=0, user_id=9, mood=4, note="ok", recorded_at=_now())
    )
    assert entry.id > 0
    assert database.moods.list_mood_entries(9)[0].mood == 4


def test_documents_and_chunks_with_embedding(database: Database) -> None:
    doc = database.documents.add_document(
        Document(id=0, user_id=2, title="note", content="hello", created_at=_now())
    )
    assert doc.id > 0
    database.documents.add_chunk(
        DocumentChunk(
            id=0, document_id=doc.id, chunk_index=0, content="hello", embedding=b"\x00\x01\x02"
        )
    )
    chunks = database.documents.list_chunks(2)
    assert len(chunks) == 1
    assert chunks[0].embedding == b"\x00\x01\x02"


def test_greeting_rules_crud(database: Database) -> None:
    rule = database.greeting_rules.add_rule(
        GreetingRule(
            id=0,
            user_id=4,
            text="hi",
            greeting_interval="daily",
            greeting_hour=8,
            greeting_weekday=0,
            greeting_day=1,
            enabled=True,
            sort_order=0,
        )
    )
    assert rule.id > 0
    assert database.greeting_rules.count_rules(4) == 1
    assert len(database.greeting_rules.list_enabled_rules()) == 1
    from dataclasses import replace

    database.greeting_rules.update_rule(
        replace(rule, enabled=False, last_sent_date=date(2026, 6, 14))
    )
    updated = database.greeting_rules.get_rule(rule.id)
    assert updated is not None and updated.enabled is False
    assert updated.last_sent_date == date(2026, 6, 14)
    assert database.greeting_rules.list_enabled_rules() == []
    database.greeting_rules.delete_rule(rule.id)
    assert database.greeting_rules.count_rules(4) == 0
