"""Owner-reviewable learning proposals (Phase 21C)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class LearningProposal:
    id: int
    user_id: int
    kind: str
    payload: dict[str, str]
    evidence: dict[str, str]
    status: str
    created_at: datetime
    resolved_at: datetime | None = None
    applied_reference: str | None = None
