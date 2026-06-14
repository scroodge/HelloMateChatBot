"""Tests for Telegram Business service helpers."""

from __future__ import annotations

from datetime import datetime

from app.database.db import Database
from app.services.business_service import BusinessService


def test_save_and_resolve_business_connection(tmp_path) -> None:
    database_path = tmp_path / "test.db"
    with Database(f"sqlite:///{database_path}") as database:
        service = BusinessService(database.business)
        now = datetime(2026, 6, 14, 12, 0, tzinfo=datetime.now().astimezone().tzinfo)
        saved = service.save_connection(
            connection_id="conn-1",
            owner_user_id=100000001,
            is_enabled=True,
            now=now,
        )
        loaded = service.get_connection("conn-1")

    assert saved.connection_id == "conn-1"
    assert loaded is not None
    assert loaded.owner_user_id == 100000001
    assert loaded.is_enabled is True


def test_save_and_lookup_managed_chat(tmp_path) -> None:
    database_path = tmp_path / "test.db"
    with Database(f"sqlite:///{database_path}") as database:
        service = BusinessService(database.business)
        service.save_connection(
            connection_id="conn-1",
            owner_user_id=100000001,
            is_enabled=True,
        )
        service.save_chat(
            chat_id=555001,
            contact_user_id=555001,
            connection_id="conn-1",
        )
        by_contact = service.get_chat_for_contact(555001)

    assert by_contact is not None
    assert by_contact.connection_id == "conn-1"
    assert by_contact.chat_id == 555001


def test_is_owner_message() -> None:
    assert BusinessService.is_owner_message(100000001, 100000001) is True
    assert BusinessService.is_owner_message(100000001, 555001) is False
    assert BusinessService.is_owner_message(100000001, None) is False
