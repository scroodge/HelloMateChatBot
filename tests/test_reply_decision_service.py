"""Hard-rule coverage for Phase 23 shadow reply decisions."""

from __future__ import annotations

from app.services.reply_decision_service import ReplyDecisionService


class FakeRepository:
    def __init__(self) -> None:
        self.saved: list[tuple[int, str, object]] = []

    def add(self, user_id: int, actual_mode: str, decision: object) -> None:
        self.saved.append((user_id, actual_mode, decision))

    def recent(self, *, limit: int = 50) -> list[dict[str, object]]:
        return []


def test_money_request_is_high_risk_and_never_auto() -> None:
    decision = ReplyDecisionService(FakeRepository()).decide(
        "Можешь перевести мне деньги?", has_context=True
    )

    assert decision.risk_level == "high"
    assert decision.recommended_mode == "off"
    assert "hard_rule:money" in decision.reasons


def test_owner_availability_question_requires_suggestion() -> None:
    decision = ReplyDecisionService(FakeRepository()).decide(
        "Ты завтра будешь свободен?", has_context=False
    )

    assert decision.risk_level == "medium"
    assert decision.recommended_mode == "suggest"
    assert decision.requires_owner_knowledge is True


def test_low_risk_message_can_be_auto_in_shadow_recommendation() -> None:
    decision = ReplyDecisionService(FakeRepository()).decide("Привет, как день?", has_context=True)

    assert decision.risk_level == "low"
    assert decision.recommended_mode == "auto"


def test_shadow_feature_flag_preserves_static_behavior_by_recording_nothing() -> None:
    repository = FakeRepository()
    service = ReplyDecisionService(repository, enabled=False)

    assert service.record(1, "Переведи деньги", "auto", has_context=False) is None
    assert repository.saved == []
