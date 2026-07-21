"""Typed inputs and outputs for reply-context compilation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ContextBlock:
    """One attributable piece of context considered for a reply prompt.

    ``priority`` is descending: higher-priority blocks render earlier.  The
    baseline compiler intentionally does not trim, deduplicate, or budget these
    blocks yet; those policy decisions are introduced in Phase 20B.
    """

    kind: str
    content: str
    priority: int
    confidence: float | None
    source_id: str | None
    freshness_at: datetime | None
    sensitivity: str
    estimated_tokens: int
    placement: str = "system"


@dataclass(frozen=True, slots=True)
class CompiledContext:
    """Deterministic compiled context with the blocks that produced it."""

    system_prompt: str
    blocks: tuple[ContextBlock, ...]
    estimated_tokens: int
    live_messages: tuple[dict[str, str], ...] = ()
