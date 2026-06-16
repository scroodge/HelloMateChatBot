"""LLM provider factory."""

from __future__ import annotations

from app.config import Config
from app.services.llm.ollama_provider import OllamaProvider
from app.services.llm.openai_provider import OpenAIProvider


def build_llm_provider(config: Config) -> OllamaProvider | OpenAIProvider:
    """Create the configured LLM provider."""

    if config.llm_provider == "openai":
        return OpenAIProvider(
            base_url=config.llm_base_url or "https://api.openai.com",
            model=config.llm_model,
            api_key=config.llm_api_key,
            max_tokens=config.llm_max_tokens,
            temperature=config.llm_temperature,
        )
    return OllamaProvider(
        base_url=config.llm_base_url,
        model=config.llm_model,
        max_tokens=config.llm_max_tokens,
        temperature=config.llm_temperature,
    )
