"""Tests for Phase 20A typed context compilation."""

from __future__ import annotations

from app.services.context_compiler import ContextCompiler, context_block, estimate_tokens


def test_compiler_orders_blocks_by_descending_priority_and_preserves_content() -> None:
    compiled = ContextCompiler().compile(
        [
            context_block("low", " low", priority=10),
            context_block("high", "high", priority=30),
            context_block("middle", " middle", priority=20),
        ]
    )

    assert [block.kind for block in compiled.blocks] == ["high", "middle", "low"]
    assert compiled.system_prompt == "high middle low"
    assert compiled.estimated_tokens == sum(block.estimated_tokens for block in compiled.blocks)


def test_compiler_ignores_empty_blocks_and_keeps_equal_priority_order() -> None:
    compiled = ContextCompiler().compile(
        [
            context_block("first", "first", priority=1),
            context_block("empty", "  ", priority=100),
            context_block("second", " second", priority=1),
        ]
    )

    assert [block.kind for block in compiled.blocks] == ["first", "second"]
    assert compiled.system_prompt == "first second"


def test_compiler_keeps_live_context_metadata_out_of_system_prompt() -> None:
    compiled = ContextCompiler().compile(
        [
            context_block("persona", "Persona", priority=100),
            context_block("live_window", "user: hello", priority=90, placement="live_window"),
        ]
    )

    assert [block.kind for block in compiled.blocks] == ["persona", "live_window"]
    assert compiled.system_prompt == "Persona"
    assert compiled.estimated_tokens > estimate_tokens(compiled.system_prompt)


def test_estimate_tokens_is_provider_neutral_and_non_negative() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("Привет, мир!") == 4
