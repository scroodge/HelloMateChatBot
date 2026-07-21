"""Provider-neutral request and result types for LLM generations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    messages: list[dict[str, str]]
    purpose: str
    contact_user_id: int | None
    prompt_version: str
    context_policy_version: str


@dataclass(frozen=True, slots=True)
class GenerationResult:
    text: str
    provider: str
    model: str
    response_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None
    finish_reason: str | None
    latency_ms: int
    trace_id: str | None = None
