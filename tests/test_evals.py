"""Regression tests for the Phase 19 Eval Lab."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.evals.core import (
    ProviderModelJudge,
    build_eval_messages,
    grade_reply,
    load_cases,
    run_cases,
    summarize,
)
from app.evals.fixture_provider import FixtureProvider
from app.models.generation import GenerationRequest, GenerationResult

DATASET = Path("evals/datasets/regression.jsonl")


def _fixture_provider():
    cases = load_cases(DATASET)
    return cases, FixtureProvider(
        {
            build_eval_messages(case)[-1]["content"]: case.fixture_reply
            for case in cases
            if case.fixture_reply
        }
    )


@pytest.mark.asyncio
async def test_checked_in_regression_baseline_is_reproducible() -> None:
    cases, provider = _fixture_provider()
    assert len(cases) >= 50

    results = await run_cases(cases, provider, prompt_version="baseline-v1")
    summary = summarize(results)

    assert summary["case_count"] == len(cases)
    assert summary["pass_rate"] == 1.0
    assert summary["hard_failure_count"] == 0
    assert all(result.latency_ms >= 0 for result in results)


def test_deliberate_safety_regression_fails_instead_of_being_averaged_away() -> None:
    case = load_cases(DATASET)[0]
    grades = grade_reply(case, "As an AI language model, I can help.")

    assert any(grade.name == "language" and grade.hard_fail for grade in grades)
    assert any(grade.name == "no_ai_meta_tail" and grade.hard_fail for grade in grades)


def test_reserved_case_cannot_disclose_fixture_private_fact() -> None:
    case = next(case for case in load_cases(DATASET) if case.case_id == "ru-reserved-05")
    grades = grade_reply(case, "Ты живёшь на улице Лесной, дом 14.")

    privacy = next(grade for grade in grades if grade.name == "reserved_privacy")
    assert privacy.hard_fail


@pytest.mark.asyncio
async def test_model_assisted_judge_returns_score_and_reason_for_each_dimension() -> None:
    class JudgeDouble:
        async def generate(self, request: GenerationRequest) -> GenerationResult:
            return GenerationResult(
                text=(
                    '{"accuracy_helpfulness":{"score":1,"reason":"accurate"},'
                    '"groundedness":{"score":1,"reason":"grounded"},'
                    '"style_persona":{"score":0.8,"reason":"warm"},'
                    '"privacy_boundary":{"score":1,"reason":"safe"},'
                    '"reference_preference":{"score":0.9,"reason":"useful"}}'
                ),
                provider="test",
                model="test",
                response_id=None,
                input_tokens=1,
                output_tokens=1,
                cached_tokens=None,
                finish_reason="stop",
                latency_ms=1,
            )

    grades = await ProviderModelJudge(JudgeDouble()).grade(load_cases(DATASET)[0], "Привет!")

    assert [grade.name for grade in grades] == [
        "accuracy_helpfulness",
        "groundedness",
        "style_persona",
        "privacy_boundary",
        "reference_preference",
    ]
    assert all(grade.reason for grade in grades)
