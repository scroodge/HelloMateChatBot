"""Explainable, shadow-only risk decision for one incoming contact message."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReplyDecision:
    intent: str
    risk_level: str
    memory_confidence: str
    requires_owner_knowledge: bool
    requires_external_action: bool
    recommended_mode: str
    reasons: tuple[str, ...]
