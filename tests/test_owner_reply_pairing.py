"""Conservative draft-to-owner pairing tests (Phase 21A)."""

from __future__ import annotations

from app.database.db import Database
from app.services.memory_service import MemoryService
from app.services.owner_reply_pairing_service import OwnerReplyPairingService
from app.services.suggestions_service import SuggestionsService


def _make(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'pairs.db'}")
    database.open()
    memory = MemoryService(database.memory)
    suggestions = SuggestionsService(database.suggestions, database.feedback)
    pairing = OwnerReplyPairingService(database.owner_reply_pairs, suggestions, memory)
    return database, memory, suggestions, pairing


def test_pair_requires_owner_confirmation_before_recording_learning_outcome(tmp_path) -> None:
    database, memory, suggestions, pairing = _make(tmp_path)
    with database:
        memory.record_user_message(1, "Как ты?")
        suggestion = suggestions.record(1, "Как ты?", "Хорошо, спасибо")
        assert suggestion is not None
        owner_message = memory.record_assistant_message(
            1, "Нормально, спасибо", authored_by="owner"
        )

        pair = pairing.observe_owner_reply(owner_message)
        assert pair is not None
        assert suggestions.get(suggestion.id).status == "pending"

        assert pairing.confirm(pair.id) is True
        assert suggestions.get(suggestion.id).status == "owner_replied"
        assert pairing.get(pair.id).status == "confirmed"


def test_pair_is_not_proposed_after_fresh_contact_message(tmp_path) -> None:
    database, memory, suggestions, pairing = _make(tmp_path)
    with database:
        memory.record_user_message(1, "Первое сообщение")
        suggestion = suggestions.record(1, "Первое сообщение", "Черновик")
        assert suggestion is not None
        memory.record_user_message(1, "Новое сообщение меняет контекст")
        owner_message = memory.record_assistant_message(1, "Мой ответ", authored_by="owner")

        assert pairing.observe_owner_reply(owner_message) is None
        assert suggestions.get(suggestion.id).status == "pending"


def test_confirmed_pair_can_be_removed_from_learning(tmp_path) -> None:
    database, memory, suggestions, pairing = _make(tmp_path)
    with database:
        memory.record_user_message(1, "Первое сообщение")
        suggestion = suggestions.record(1, "Первое сообщение", "Черновик")
        assert suggestion is not None
        owner_message = memory.record_assistant_message(1, "Мой ответ", authored_by="owner")
        pair = pairing.observe_owner_reply(owner_message)
        assert pair is not None
        assert pairing.confirm(pair.id) is True

        assert pairing.retract(pair.id, "связь оказалась неверной") is True
        assert pairing.get(pair.id).status == "retracted"
        assert suggestions.get(suggestion.id).status == "pair_retracted"
        assert database.feedback.analytics(user_id=None, since=None)["owner_replied"] == 0
