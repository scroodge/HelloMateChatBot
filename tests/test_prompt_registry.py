"""Prompt registry versioning tests (Phase 20D)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.llm import complete_text
from app.services.prompt_registry import (
    CONTEXT_POLICY_REGISTRY,
    CONTEXT_POLICY_VERSION,
    PROMPT_REGISTRY,
    REPLY_PROMPT_VERSION,
)


@pytest.mark.asyncio
async def test_complete_text_passes_explicit_registry_versions() -> None:
    service = AsyncMock()
    service.complete.return_value = "reply"

    reply = await complete_text(
        service,
        [{"role": "user", "content": "Hi"}],
        purpose="reply",
        contact_user_id=1,
        prompt_version=REPLY_PROMPT_VERSION,
        context_policy_version=CONTEXT_POLICY_VERSION,
    )

    assert reply == "reply"
    service.complete.assert_awaited_once_with(
        [{"role": "user", "content": "Hi"}],
        purpose="reply",
        contact_user_id=1,
        prompt_version=REPLY_PROMPT_VERSION,
        context_policy_version=CONTEXT_POLICY_VERSION,
    )


def test_active_versions_are_documented_in_the_registry() -> None:
    assert REPLY_PROMPT_VERSION in PROMPT_REGISTRY
    assert CONTEXT_POLICY_VERSION in CONTEXT_POLICY_REGISTRY
