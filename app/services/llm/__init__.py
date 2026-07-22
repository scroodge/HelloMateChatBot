"""LLM provider abstractions."""

from __future__ import annotations

from datetime import datetime
from time import monotonic
from typing import Protocol
from uuid import uuid4

from app.models.generation import GenerationRequest, GenerationResult
from app.services.llm.http_client import ProviderRequestError
from app.services.prompt_registry import (
    BASELINE_CONTEXT_POLICY_VERSION,
    BASELINE_PROMPT_VERSION,
)


class LLMProvider(Protocol):
    """Contract for text completion providers."""

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """Return a provider-neutral model generation."""
        ...


class LLMService:
    """Facade over a configured LLM provider."""

    def __init__(
        self,
        provider: LLMProvider,
        feedback_repository: object | None = None,
        fallback_provider: LLMProvider | None = None,
    ) -> None:
        self.provider = provider
        self.feedback_repository = feedback_repository
        self.fallback_provider = fallback_provider

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """Generate and persist metadata only, never the prompt or reply text."""
        trace_id = uuid4().hex
        started_at = datetime.now().astimezone()
        started = monotonic()
        fallback_chain: str | None = None
        try:
            result = await self.provider.generate(request)
        except ProviderRequestError as exc:
            if not exc.retryable or self.fallback_provider is None:
                self._record_error(trace_id, request, started_at, started, exc)
                raise
            try:
                result = await self.fallback_provider.generate(request)
            except Exception as fallback_exc:
                self._record_error(trace_id, request, started_at, started, fallback_exc)
                raise
            fallback_chain = self._fallback_chain()
        except Exception as exc:
            self._record_error(trace_id, request, started_at, started, exc)
            raise
        total_latency_ms = round((monotonic() - started) * 1000)
        self._record_trace(
            trace_id,
            request,
            started_at,
            total_latency_ms,
            provider=result.provider,
            model=result.model,
            response_id=result.response_id,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cached_tokens=result.cached_tokens,
            finish_reason=result.finish_reason,
            fallback_chain=fallback_chain,
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
            latency_ms=total_latency_ms,
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
                "fallback_chain": metadata.pop("fallback_chain", None),
                "created_at": created_at.isoformat(),
            }
        )

    def _record_error(
        self,
        trace_id: str,
        request: GenerationRequest,
        started_at: datetime,
        started: float,
        exc: Exception,
    ) -> None:
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

    def _fallback_chain(self) -> str:
        primary_name = getattr(self.provider, "provider_name", self.provider.__class__.__name__)
        primary_model = getattr(self.provider, "model", "unknown")
        fallback = self.fallback_provider
        assert fallback is not None
        fallback_name = getattr(fallback, "provider_name", fallback.__class__.__name__)
        fallback_model = getattr(fallback, "model", "unknown")
        return f"{primary_name}/{primary_model} -> {fallback_name}/{fallback_model}"

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        purpose: str = "reply",
        contact_user_id: int | None = None,
        prompt_version: str = BASELINE_PROMPT_VERSION,
        context_policy_version: str = BASELINE_CONTEXT_POLICY_VERSION,
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
    prompt_version: str = BASELINE_PROMPT_VERSION,
    context_policy_version: str = BASELINE_CONTEXT_POLICY_VERSION,
) -> str:
    """Call the modern metadata API while tolerating legacy injected doubles."""
    try:
        return await llm_service.complete(
            messages,
            purpose=purpose,
            contact_user_id=contact_user_id,
            prompt_version=prompt_version,
            context_policy_version=context_policy_version,
        )
    except TypeError as exc:
        if "unexpected keyword argument" not in str(exc):
            raise
        return await llm_service.complete(messages)
