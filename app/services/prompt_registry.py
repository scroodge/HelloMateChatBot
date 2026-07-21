"""Named, reviewable prompt and context-policy versions (Phase 20D)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PromptVersion:
    identifier: str
    changelog: str


BASELINE_PROMPT_VERSION = "v1"
BASELINE_CONTEXT_POLICY_VERSION = "v1"
REPLY_PROMPT_VERSION = "reply-v1"
CONTEXT_POLICY_VERSION = "context-compiler-v2"

PROMPT_REGISTRY = {
    BASELINE_PROMPT_VERSION: PromptVersion(
        BASELINE_PROMPT_VERSION, "Legacy baseline retained for compatibility and replay."
    ),
    REPLY_PROMPT_VERSION: PromptVersion(
        REPLY_PROMPT_VERSION,
        "Typed reply context with explicit accuracy and openness policies.",
    ),
}

CONTEXT_POLICY_REGISTRY = {
    BASELINE_CONTEXT_POLICY_VERSION: PromptVersion(
        BASELINE_CONTEXT_POLICY_VERSION, "Legacy context assembly."
    ),
    CONTEXT_POLICY_VERSION: PromptVersion(
        CONTEXT_POLICY_VERSION,
        "Budgeted compiler with deduplication, conflict handling, and temporal fact provenance.",
    ),
}
