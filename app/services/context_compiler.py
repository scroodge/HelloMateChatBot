"""Deterministic baseline compiler for typed reply-context blocks (Phase 20A)."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from datetime import datetime

from app.models.context import CompiledContext, ContextBlock, ContextBlockDecision

_TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)
_WHITESPACE_PATTERN = re.compile(r"\s+")
_STALE_DAYS = 90
_STALE_PRIORITY_PENALTY = 200
_LOW_CONFIDENCE_PRIORITY_PENALTY = 100


def estimate_tokens(text: str) -> int:
    """Return a cheap, provider-neutral token estimate for a context block."""

    return len(_TOKEN_PATTERN.findall(text))


def context_block(
    kind: str,
    content: str,
    *,
    priority: int,
    confidence: float | None = None,
    source_id: str | None = None,
    freshness_at: datetime | None = None,
    sensitivity: str = "private",
    placement: str = "system",
    conflict_key: str | None = None,
    required: bool = False,
) -> ContextBlock:
    """Create a block and calculate its estimate at the assembly boundary."""

    return ContextBlock(
        kind=kind,
        content=content,
        priority=priority,
        confidence=confidence,
        source_id=source_id,
        freshness_at=freshness_at,
        sensitivity=sensitivity,
        estimated_tokens=estimate_tokens(content),
        placement=placement,
        conflict_key=conflict_key,
        required=required,
    )


class ContextCompiler:
    """Compile a bounded, attributable reply context with deterministic policy."""

    def __init__(
        self, *, token_budget: int = 4000, now: Callable[[], datetime] | None = None
    ) -> None:
        if token_budget < 1:
            raise ValueError("token_budget must be positive")
        self.token_budget = token_budget
        self._now = now or (lambda: datetime.now().astimezone())

    def compile(self, blocks: Iterable[ContextBlock]) -> CompiledContext:
        """Select blocks within budget; required safety/prompt policy always remains."""

        candidates = [(index, block) for index, block in enumerate(blocks) if block.content.strip()]
        now = self._now()
        ordered = sorted(candidates, key=lambda item: (-self._priority(item[1], now), item[0]))
        included: list[ContextBlock] = []
        decisions: list[ContextBlockDecision] = []
        seen_content: dict[str, ContextBlock] = {}
        seen_conflicts: dict[str, ContextBlock] = {}
        used_tokens = 0
        required_tokens = sum(block.estimated_tokens for _, block in candidates if block.required)
        optional_budget = max(0, self.token_budget - required_tokens)
        optional_tokens = 0

        for _, block in ordered:
            duplicate_of = seen_content.get(_normalise_content(block.content))
            if duplicate_of is not None and not block.required:
                decisions.append(
                    ContextBlockDecision(block, False, f"duplicate_of:{duplicate_of.kind}")
                )
                continue

            if block.conflict_key:
                conflict_with = seen_conflicts.get(block.conflict_key)
                if conflict_with is not None and not block.required:
                    decisions.append(
                        ContextBlockDecision(block, False, f"conflicts_with:{conflict_with.kind}")
                    )
                    continue

            would_exceed_budget = optional_tokens + block.estimated_tokens > optional_budget
            if would_exceed_budget and not block.required:
                decisions.append(ContextBlockDecision(block, False, "excluded:token_budget"))
                continue

            included.append(block)
            used_tokens += block.estimated_tokens
            if not block.required:
                optional_tokens += block.estimated_tokens
            seen_content.setdefault(_normalise_content(block.content), block)
            if block.conflict_key:
                seen_conflicts.setdefault(block.conflict_key, block)
            if block.required:
                reason = (
                    "included:required"
                    if required_tokens > self.token_budget
                    else "included:required_policy"
                )
            else:
                penalty = self._priority_penalty(block, now)
                reason = "included:priority" if penalty == 0 else "included:deprioritized"
            decisions.append(ContextBlockDecision(block, True, reason))

        selected = tuple(included)
        return CompiledContext(
            system_prompt="".join(
                block.content for block in selected if block.placement == "system"
            ),
            blocks=selected,
            estimated_tokens=used_tokens,
            decisions=tuple(decisions),
            considered_tokens=sum(block.estimated_tokens for _, block in candidates),
        )

    def _priority(self, block: ContextBlock, now: datetime) -> int:
        return block.priority - self._priority_penalty(block, now)

    def _priority_penalty(self, block: ContextBlock, now: datetime) -> int:
        penalty = 0
        if block.confidence is not None and block.confidence < 0.5:
            penalty += _LOW_CONFIDENCE_PRIORITY_PENALTY
        if block.freshness_at is not None and (now - block.freshness_at).days > _STALE_DAYS:
            penalty += _STALE_PRIORITY_PENALTY
        return penalty


def _normalise_content(content: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", content).strip().casefold()
