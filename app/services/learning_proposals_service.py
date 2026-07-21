"""Apply owner-approved learning proposals without silent prompt changes."""

from __future__ import annotations

from app.models.learning_proposal import LearningProposal

_EXAMPLE_KINDS = {"positive_example": "positive", "negative_example": "negative"}
_RULE_KINDS = {"style_rule", "boundary"}
_FACT_KINDS = {"fact_confirmation", "fact_correction"}
_VALID_KINDS = frozenset(_EXAMPLE_KINDS) | _RULE_KINDS | _FACT_KINDS


class LearningProposalsService:
    def __init__(self, repository: object, examples_service: object, facts_service: object) -> None:
        self.repository = repository
        self.examples_service = examples_service
        self.facts_service = facts_service

    def propose(
        self, user_id: int, kind: str, payload: dict[str, str], evidence: dict[str, str]
    ) -> LearningProposal:
        if kind not in _VALID_KINDS:
            raise ValueError(f"Unsupported learning proposal kind: {kind}")
        clean_payload = {
            key: value.strip()[:600] for key, value in payload.items() if value and value.strip()
        }
        clean_evidence = {
            key: value.strip()[:1200] for key, value in evidence.items() if value and value.strip()
        }
        if not clean_evidence:
            raise ValueError("Learning proposals require evidence")
        if kind in _EXAMPLE_KINDS and not {"contact_message", "reply_text"} <= clean_payload.keys():
            raise ValueError("Example proposals require contact_message and reply_text")
        if kind in _RULE_KINDS and not clean_payload.get("rule"):
            raise ValueError("Rule proposals require rule")
        if kind in _FACT_KINDS and not {"key", "value"} <= clean_payload.keys():
            raise ValueError("Fact proposals require key and value")
        return self.repository.add(user_id, kind, clean_payload, clean_evidence)

    def list_reviewable(self) -> list[LearningProposal]:
        return self.repository.list_reviewable()

    def approve(self, proposal_id: int) -> bool:
        proposal = self.repository.get(proposal_id)
        if proposal is None or proposal.status != "pending":
            return False
        reference = None
        if proposal.kind in _EXAMPLE_KINDS:
            example = self.examples_service.add_example(
                proposal.user_id,
                proposal.payload["contact_message"],
                proposal.payload["reply_text"],
                _EXAMPLE_KINDS[proposal.kind],
            )
            reference = f"example:{example.id}"
        elif proposal.kind in _FACT_KINDS:
            self.facts_service.set_fact(
                proposal.user_id,
                proposal.payload["key"],
                proposal.payload["value"],
                owner_confirmed=True,
            )
            reference = f"fact:{proposal.payload['key']}"
        self.repository.resolve(proposal_id, "approved", reference)
        return True

    def reject(self, proposal_id: int) -> bool:
        proposal = self.repository.get(proposal_id)
        if proposal is None or proposal.status != "pending":
            return False
        self.repository.resolve(proposal_id, "rejected")
        return True

    def approved_rules_block(self, user_id: int, language: str) -> str:
        rules = [
            proposal
            for proposal in self.repository.list_reviewable()
            if proposal.user_id == user_id
            and proposal.status == "approved"
            and proposal.kind in _RULE_KINDS
        ]
        if not rules:
            return ""
        header = (
            "Подтверждённые владельцем правила для этого контакта:"
            if language == "ru"
            else "Owner-approved rules for this contact:"
        )
        return " " + header + " " + " ".join(f"- {proposal.payload['rule']}" for proposal in rules)
