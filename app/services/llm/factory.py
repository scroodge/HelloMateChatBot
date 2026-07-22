"""LLM provider factory."""

from __future__ import annotations

from app.config import Config
from app.services.llm.ollama_provider import OllamaProvider
from app.services.llm.openai_provider import OpenAIProvider


def _build_provider(
    config: Config, provider_name: str, base_url: str, model: str, api_key: str
) -> OllamaProvider | OpenAIProvider:
    """Create one provider with the application's resilience settings."""

    if provider_name == "openai":
        return OpenAIProvider(
            base_url=base_url or "https://api.openai.com",
            model=model,
            api_key=api_key,
            max_tokens=config.llm_max_tokens,
            temperature=config.llm_temperature,
            timeout_seconds=config.llm_timeout_seconds,
            max_concurrency=config.llm_max_concurrency,
            max_retries=config.llm_max_retries,
        )
    return OllamaProvider(
        base_url=base_url,
        model=model,
        max_tokens=config.llm_max_tokens,
        temperature=config.llm_temperature,
        timeout_seconds=config.llm_timeout_seconds,
        max_concurrency=config.llm_max_concurrency,
        max_retries=config.llm_max_retries,
    )


def build_llm_provider(config: Config) -> OllamaProvider | OpenAIProvider:
    """Create the configured primary LLM provider."""

    return _build_provider(
        config, config.llm_provider, config.llm_base_url, config.llm_model, config.llm_api_key
    )


def build_fallback_llm_provider(config: Config) -> OllamaProvider | OpenAIProvider | None:
    """Create an explicitly enabled fallback, otherwise preserve primary-only routing."""

    if not config.llm_fallback_provider:
        return None
    return _build_provider(
        config,
        config.llm_fallback_provider,
        config.llm_fallback_base_url,
        config.llm_fallback_model,
        config.llm_fallback_api_key,
    )
