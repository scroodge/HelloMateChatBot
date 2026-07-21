"""LLM provider abstractions."""

from __future__ import annotations

from datetime import datetime
from time import monotonic
from typing import Protocol
from uuid import uuid4

from app.models.generation import GenerationRequest, GenerationResult


class LLMProvider(Protocol):
    """Contract for text completion providers."""

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """Return a provider-neutral model generation."""
        ...


class LLMService:
    """Facade over a configured LLM provider."""

    def __init__(self, provider: LLMProvider, feedback_repository: object | None = None) -> None:
        self.provider = provider
        self.feedback_repository = feedback_repository

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """Generate and persist metadata only, never the prompt or reply text."""
        trace_id = uuid4().hex
        started_at = datetime.now().astimezone()
        started = monotonic()
        try:
            result = await self.provider.generate(request)
        except Exception as exc:
            self._record_trace(
                trace_id,
                request,
                started_at,
                round((monotonic() - started) * 1000),
                provider=getattr(
                    self.provider, "provider_name", self.provider.__class__.__name__.lower()
                ),
                model=getattr(self.provider, "model", "unknown"),
                error_code=exc.__class__.__name__,
            )
            raise
        self._record_trace(
            trace_id,
            request,
            started_at,
            result.latency_ms,
            provider=result.provider,
            model=result.model,
            response_id=result.response_id,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cached_tokens=result.cached_tokens,
            finish_reason=result.finish_reason,
        )
        return GenerationResult(
            text=result.text,
            provider=result.provider,
            model=result.model,
            response_id=result.response_id,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cached_tokens=result.cached_tokens,
            finish_reason=result.finish_reason,
            latency_ms=result.latency_ms,
            trace_id=trace_id,
        )

    def _record_trace(
        self,
        trace_id: str,
        request: GenerationRequest,
        created_at: datetime,
        latency_ms: int,
        **metadata: object,
    ) -> None:
        if self.feedback_repository is None:
            return
        self.feedback_repository.add_generation_run(
            {
                "trace_id": trace_id,
                "user_id": request.contact_user_id,
                "suggestion_id": None,
                "purpose": request.purpose,
                "provider": metadata.pop("provider"),
                "model": metadata.pop("model"),
                "prompt_version": request.prompt_version,
                "context_policy_version": request.context_policy_version,
                "response_id": metadata.pop("response_id", None),
                "input_tokens": metadata.pop("input_tokens", None),
                "output_tokens": metadata.pop("output_tokens", None),
                "cached_tokens": metadata.pop("cached_tokens", None),
                "latency_ms": latency_ms,
                "finish_reason": metadata.pop("finish_reason", None),
                "error_code": metadata.pop("error_code", None),
                "fallback_chain": None,
                "created_at": created_at.isoformat(),
            }
        )

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        purpose: str = "reply",
        contact_user_id: int | None = None,
        prompt_version: str = "v1",
        context_policy_version: str = "v1",
    ) -> str:
        """Compatibility helper for text-only callers."""

        result = await self.generate(
            GenerationRequest(
                messages, purpose, contact_user_id, prompt_version, context_policy_version
            )
        )
        return result.text


async def complete_text(
    llm_service: object,
    messages: list[dict[str, str]],
    *,
    purpose: str,
    contact_user_id: int | None,
) -> str:
    """Call the modern metadata API while tolerating legacy injected doubles."""
    try:
        return await llm_service.complete(
            messages, purpose=purpose, contact_user_id=contact_user_id
        )
    except TypeError as exc:
        if "unexpected keyword argument" not in str(exc):
            raise
        return await llm_service.complete(messages)
