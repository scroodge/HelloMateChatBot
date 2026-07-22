"""Privacy-safe, versioned snapshot of the Phase 24 model decision gate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class ModelDecisionReport:
    id: int
    criteria_version: str
    report: dict[str, Any]
    created_at: datetime
