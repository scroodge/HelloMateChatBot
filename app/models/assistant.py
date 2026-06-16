"""Owner personal-assistant profile model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AssistantProfile:
    """A named owner-only assistant persona (e.g. "english teacher").

    Each profile has its own isolated conversation memory, keyed separately
    from any contact, so assistant chatter never pollutes contact learning.
    """

    owner_id: int
    name: str
    persona: str
    created_at: datetime
    id: int | None = None
