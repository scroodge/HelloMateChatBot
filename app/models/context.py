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
    conflict_key: str | None = None
    required: bool = False


@dataclass(frozen=True, slots=True)
class ContextBlockDecision:
    """Explain whether a block entered the prompt and why."""

    block: ContextBlock
    included: bool
    reason: str


@dataclass(frozen=True, slots=True)
class CompiledContext:
    """Deterministic compiled context with the blocks that produced it."""

    system_prompt: str
    blocks: tuple[ContextBlock, ...]
    estimated_tokens: int
    live_messages: tuple[dict[str, str], ...] = ()
    reply_context: str | None = None
    decisions: tuple[ContextBlockDecision, ...] = ()
    considered_tokens: int = 0
