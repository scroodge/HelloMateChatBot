"""LLM provider abstractions."""

from __future__ import annotations

from typing import Protocol


class LLMProvider(Protocol):
    """Contract for text completion providers."""

    async def complete(self, messages: list[dict[str, str]]) -> str:
        """Return a model completion for the given chat messages."""
        ...


class LLMService:
    """Facade over a configured LLM provider."""

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    async def complete(self, messages: list[dict[str, str]]) -> str:
        """Generate a completion using the configured provider."""

        return await self.provider.complete(messages)
