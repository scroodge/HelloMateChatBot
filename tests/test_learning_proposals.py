"""Phase 21C owner-reviewed learning proposal lifecycle."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.database.db import Database
from app.services.examples_service import ContactExamplesService
from app.services.learning_proposals_service import LearningProposalsService


def _make_service(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'proposals.db'}")
    database.open()
    facts_service = MagicMock()
    return (
        database,
        LearningProposalsService(
            database.learning_proposals,
            ContactExamplesService(database.examples),
            facts_service,
        ),
        facts_service,
    )


def test_positive_example_requires_evidence_and_explicit_approval(tmp_path) -> None:
    database, service, _ = _make_service(tmp_path)
    with database:
        proposal = service.propose(
            42,
            "positive_example",
            {"contact_message": "Как день?", "reply_text": "Хорошо, а у тебя?"},
            {"source": "confirmed owner reply pair #7"},
        )
        assert database.examples.list_examples(42) == []

        assert service.approve(proposal.id) is True
        examples = database.examples.list_examples(42)
        saved = service.repository.get(proposal.id)

    assert examples[0].reply_text == "Хорошо, а у тебя?"
    assert saved is not None
    assert saved.applied_reference == f"example:{examples[0].id}"


def test_rule_only_enters_prompt_after_owner_approval(tmp_path) -> None:
    database, service, _ = _make_service(tmp_path)
    with database:
        proposal = service.propose(
            42,
            "boundary",
            {"rule": "Не обещай встречу от имени владельца."},
            {"source": "owner correction in chat"},
        )
        assert service.approved_rules_block(42, "ru") == ""

        assert service.approve(proposal.id) is True
        block = service.approved_rules_block(42, "ru")

    assert "Подтверждённые владельцем" in block
    assert "Не обещай встречу" in block


def test_fact_proposal_marks_the_fact_as_owner_confirmed(tmp_path) -> None:
    database, service, facts_service = _make_service(tmp_path)
    with database:
        proposal = service.propose(
            42,
            "fact_correction",
            {"key": "city", "value": "Минск"},
            {"source": "contact explicitly corrected city"},
        )
        assert service.approve(proposal.id) is True

    facts_service.set_fact.assert_called_once_with(42, "city", "Минск", owner_confirmed=True)
