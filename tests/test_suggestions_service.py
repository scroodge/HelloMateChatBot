"""Tests for the suggest inbox service."""

from __future__ import annotations

from app.database.db import Database
from app.services.suggestions_service import SuggestionsService


def _make(tmp_path) -> tuple[SuggestionsService, Database]:
    db = Database(f"sqlite:///{tmp_path / 'sugg.db'}")
    db.open()
    return SuggestionsService(db.suggestions), db


def test_record_and_list_pending(tmp_path) -> None:
    svc, db = _make(tmp_path)
    with db:
        svc.record(1, "привет", "о, привет!")
        svc.record(2, "как ты?", "норм")
        pending = svc.list_pending()
        assert len(pending) == 2
        assert svc.count_pending() == 2


def test_new_suggestion_supersedes_prior_for_same_contact(tmp_path) -> None:
    svc, db = _make(tmp_path)
    with db:
        svc.record(1, "первое", "ответ 1")
        svc.record(1, "второе", "ответ 2")
        pending = svc.list_pending()
        assert len(pending) == 1
        assert pending[0].contact_message == "второе"
        # other contacts are unaffected
        svc.record(2, "u2", "r2")
        assert svc.count_pending() == 2


def test_dismiss(tmp_path) -> None:
    svc, db = _make(tmp_path)
    with db:
        s = svc.record(1, "привет", "ответ")
        svc.dismiss(s.id)
        assert svc.count_pending() == 0
        assert svc.list_pending() == []


def test_mark_saved(tmp_path) -> None:
    svc, db = _make(tmp_path)
    with db:
        s = svc.record(1, "привет", "ответ")
        svc.mark_saved(s.id)
        assert svc.count_pending() == 0


def test_empty_fields_not_recorded(tmp_path) -> None:
    svc, db = _make(tmp_path)
    with db:
        assert svc.record(1, "   ", "ответ") is None
        assert svc.record(1, "сообщение", "") is None
        assert svc.count_pending() == 0


def test_disabled_records_nothing(tmp_path) -> None:
    svc, db = _make(tmp_path)
    with db:
        svc.enabled = False
        assert svc.record(1, "привет", "ответ") is None
        assert svc.count_pending() == 0


def test_fields_truncated(tmp_path) -> None:
    svc, db = _make(tmp_path)
    with db:
        s = svc.record(1, "x" * 5000, "y" * 5000)
        assert len(s.contact_message) == 2000
        assert len(s.draft_text) == 2000


def test_get(tmp_path) -> None:
    svc, db = _make(tmp_path)
    with db:
        s = svc.record(1, "привет", "ответ")
        got = svc.get(s.id)
        assert got is not None
        assert got.draft_text == "ответ"
        assert svc.get(99999) is None
