"""Tests for Phase 20A typed context compilation."""

from __future__ import annotations

from datetime import datetime, timedelta

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


def test_compiler_excludes_low_priority_context_when_over_budget() -> None:
    compiled = ContextCompiler(token_budget=3).compile(
        [
            context_block("persona", "one two", priority=100, required=True),
            context_block("recall", " three four", priority=10),
        ]
    )

    assert [block.kind for block in compiled.blocks] == ["persona"]
    assert compiled.estimated_tokens == 2
    assert compiled.decisions[-1].reason == "excluded:token_budget"


def test_compiler_keeps_required_safety_policy_when_over_budget() -> None:
    compiled = ContextCompiler(token_budget=2).compile(
        [
            context_block("persona", "one two", priority=100, required=True),
            context_block("openness_policy", " three", priority=0, required=True),
        ]
    )

    assert [block.kind for block in compiled.blocks] == ["persona", "openness_policy"]
    assert compiled.estimated_tokens == 3
    assert compiled.decisions[-1].reason == "included:required"


def test_compiler_reserves_budget_for_required_policy_before_optional_context() -> None:
    compiled = ContextCompiler(token_budget=5).compile(
        [
            context_block("persona", "one two", priority=100, required=True),
            context_block("recall", " three four", priority=90),
            context_block("openness_policy", " five six", priority=0, required=True),
        ]
    )

    assert [block.kind for block in compiled.blocks] == ["persona", "openness_policy"]
    assert compiled.estimated_tokens == 4
    assert compiled.decisions[1].reason == "excluded:token_budget"


def test_compiler_deduplicates_and_resolves_conflicts_deterministically() -> None:
    compiled = ContextCompiler().compile(
        [
            context_block("facts", " City=Минск", priority=40, conflict_key="city"),
            context_block("recall", "city=минск", priority=30),
            context_block("stale_fact", " City=Брест", priority=20, conflict_key="city"),
        ]
    )

    assert [block.kind for block in compiled.blocks] == ["facts"]
    assert [decision.reason for decision in compiled.decisions] == [
        "included:priority",
        "duplicate_of:facts",
        "conflicts_with:facts",
    ]


def test_compiler_deprioritizes_stale_low_confidence_context() -> None:
    now = datetime.now().astimezone()
    compiled = ContextCompiler(token_budget=2, now=lambda: now).compile(
        [
            context_block("fresh", "one two", priority=100),
            context_block(
                "stale",
                " three four",
                priority=250,
                confidence=0.4,
                freshness_at=now - timedelta(days=91),
            ),
        ]
    )

    assert [block.kind for block in compiled.blocks] == ["fresh"]
    assert compiled.decisions[-1].reason == "excluded:token_budget"
