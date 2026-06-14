"""Tests for database schema provisioning."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect

from app.database.db import Database


def test_schema_created_on_open(tmp_path: Path) -> None:
    database_path = tmp_path / "test.db"
    with Database(f"sqlite:///{database_path}") as database:
        tables = set(inspect(database.engine).get_table_names())

    expected = {
        "user_greetings",
        "user_settings",
        "bot_settings",
        "user_profiles",
        "mood_entries",
        "conversation_messages",
        "conversation_summaries",
        "documents",
        "document_chunks",
        "user_greeting_rules",
        "business_connections",
        "business_chats",
        "contact_facts",
        "contact_facts_meta",
        "contact_style_profiles",
    }
    assert expected <= tables


def test_indexes_created(tmp_path: Path) -> None:
    database_path = tmp_path / "test.db"
    with Database(f"sqlite:///{database_path}") as database:
        inspector = inspect(database.engine)
        message_indexes = {idx["name"] for idx in inspector.get_indexes("conversation_messages")}

    assert "idx_conversation_messages_user_created" in message_indexes
