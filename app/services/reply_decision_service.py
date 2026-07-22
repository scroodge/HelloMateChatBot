"""Deterministic Phase 23 shadow routing decisions."""

from __future__ import annotations

import re
from typing import Protocol

from app.models.reply_decision import ReplyDecision


class ReplyDecisionRepository(Protocol):
    def add(self, user_id: int, actual_mode: str, decision: ReplyDecision) -> None: ...

    def recent(self, *, limit: int = 50) -> list[dict[str, object]]: ...


class ReplyDecisionService:
    """Applies hard safety rules but never changes routing in shadow mode."""

    _HIGH_RISK = {
        "money": (
            r"\b(деньг\w*|оплат\w*|перевод\w*|перевест\w*|куп\w*|цена\w*|"
            r"долг\w*|карта\w*|банк\w*|money|pay|transfer)\b"
        ),
        "medical": r"\b(врач|лекарств|болит|диагноз|лечен|medical|doctor|medicine)\b",
        "legal": r"\b(юрист|суд|договор|закон|legal|lawyer|court)\b",
        "private": r"\b(секрет|парол|адрес|паспорт|личн.*данн|secret|password|address)\b",
    }
    _EXTERNAL_ACTION = r"\b(закаж|заброниру|купи|оплати|перевед|отправь.*деньг|book|buy|pay|send)\b"
    _OWNER_KNOWLEDGE = (
        r"\b(где ты|когда ты|свободен|свободна|будешь|обеща|встрет|"
        r"where are you|when are you|are you free)\b"
    )
    _MEDIUM_RISK = r"\b(обид|ненавиж|злюсь|поссор|люблю|скучаю|intim|hate|angry|upset)\b"

    def __init__(self, repository: ReplyDecisionRepository, *, enabled: bool = True) -> None:
        self._repository = repository
        self.enabled = enabled

    def decide(self, message_text: str, *, has_context: bool) -> ReplyDecision:
        text = message_text.casefold()
        high_matches = [
            name for name, pattern in self._HIGH_RISK.items() if re.search(pattern, text)
        ]
        requires_external_action = bool(re.search(self._EXTERNAL_ACTION, text))
        requires_owner_knowledge = bool(re.search(self._OWNER_KNOWLEDGE, text))
        is_emotional = bool(re.search(self._MEDIUM_RISK, text))
        reasons = [f"hard_rule:{name}" for name in high_matches]
        if requires_external_action:
            reasons.append("external_action")
        if requires_owner_knowledge:
            reasons.append("requires_owner_knowledge")
        if is_emotional:
            reasons.append("emotional_or_conflict")

        memory_confidence = "high" if has_context else "unknown"
        if high_matches or requires_external_action:
            return ReplyDecision(
                "sensitive_request", "high", memory_confidence, requires_owner_knowledge,
                requires_external_action, "off", tuple(reasons)
            )
        if requires_owner_knowledge or is_emotional:
            return ReplyDecision(
                "owner_context", "medium", memory_confidence, requires_owner_knowledge,
                requires_external_action, "suggest", tuple(reasons)
            )
        return ReplyDecision(
            "conversation", "low", memory_confidence, False, False, "auto", ("low_risk",)
        )

    def record(
        self, user_id: int, message_text: str, actual_mode: str, *, has_context: bool
    ) -> ReplyDecision | None:
        if not self.enabled:
            return None
        decision = self.decide(message_text, has_context=has_context)
        self._repository.add(user_id, actual_mode, decision)
        return decision

    def recent(self, *, limit: int = 50) -> list[dict[str, object]]:
        return self._repository.recent(limit=limit)
