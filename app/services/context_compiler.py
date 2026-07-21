"""Deterministic baseline compiler for typed reply-context blocks (Phase 20A)."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime

from app.models.context import CompiledContext, ContextBlock

_TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


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
    )


class ContextCompiler:
    """Compile system-prompt blocks without changing the current prompt policy."""

    def compile(self, blocks: Iterable[ContextBlock]) -> CompiledContext:
        """Keep non-empty blocks and concatenate them in deterministic priority order."""

        indexed = [(index, block) for index, block in enumerate(blocks) if block.content.strip()]
        ordered = sorted(indexed, key=lambda item: (-item[1].priority, item[0]))
        included = tuple(block for _, block in ordered)
        return CompiledContext(
            system_prompt="".join(
                block.content for block in included if block.placement == "system"
            ),
            blocks=included,
            estimated_tokens=sum(block.estimated_tokens for block in included),
        )
