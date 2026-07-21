#!/usr/bin/env python3
"""Run HelloMate's provider-neutral evaluation dataset locally or in CI."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Support `python scripts/run_eval.py` without requiring a package install.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evals.core import (  # noqa: E402
    EvaluationCase,
    EvaluationError,
    ProviderModelJudge,
    build_eval_messages,
    load_cases,
    render_report,
    run_cases,
    summarize,
)
from app.evals.fixture_provider import FixtureProvider  # noqa: E402
from app.services.llm.ollama_provider import OllamaProvider  # noqa: E402
from app.services.llm.openai_provider import OpenAIProvider  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--provider", choices=("fixture", "ollama", "openai"), default="fixture")
    parser.add_argument("--model", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--prompt-version", default="baseline-v1")
    parser.add_argument("--prompt-file", type=Path)
    parser.add_argument("--compare-provider", choices=("fixture", "ollama", "openai"))
    parser.add_argument("--compare-model", default="")
    parser.add_argument("--compare-base-url", default="")
    parser.add_argument("--compare-api-key", default="")
    parser.add_argument("--compare-prompt-file", type=Path)
    parser.add_argument("--judge-provider", choices=("ollama", "openai"))
    parser.add_argument("--judge-model", default="")
    parser.add_argument("--judge-base-url", default="")
    parser.add_argument("--judge-api-key", default="")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-report", type=Path, required=True)
    parser.add_argument("--min-pass-rate", type=float, default=1.0)
    parser.add_argument("--allow-owner-approved", action="store_true")
    return parser.parse_args()


def _addendum(path: Path | None) -> str:
    return path.read_text(encoding="utf-8") if path else ""


def _fixture_provider(cases: list[EvaluationCase], addendum: str) -> FixtureProvider:
    replies: dict[str, str] = {}
    for case in cases:
        if not case.fixture_reply:
            raise EvaluationError(f"fixture provider requires fixture_reply: {case.case_id}")
        key = build_eval_messages(case, addendum)[-1]["content"]
        replies[key] = case.fixture_reply
    return FixtureProvider(replies)


def _provider(
    kind: str, cases: list[EvaluationCase], model: str, base_url: str, api_key: str, addendum: str
):
    if kind == "fixture":
        return _fixture_provider(cases, addendum)
    if not model or not base_url:
        raise EvaluationError("--model and --base-url are required for live providers")
    if kind == "openai":
        return OpenAIProvider(base_url, model, api_key, max_tokens=512, temperature=0.0)
    return OllamaProvider(base_url, model, max_tokens=512, temperature=0.0)


async def _run(args: argparse.Namespace) -> int:
    cases = load_cases(args.dataset, allow_owner_approved=args.allow_owner_approved)
    addendum = _addendum(args.prompt_file)
    generator = _provider(args.provider, cases, args.model, args.base_url, args.api_key, addendum)
    judge = None
    if args.judge_provider:
        judge = ProviderModelJudge(
            _provider(
                args.judge_provider,
                cases,
                args.judge_model,
                args.judge_base_url,
                args.judge_api_key,
                "",
            )
        )
    results = await run_cases(
        cases,
        generator,
        prompt_version=args.prompt_version,
        prompt_addendum=addendum,
        model_judge=judge,
    )
    payload: dict[str, object] = {
        "candidate": args.prompt_version,
        "dataset": str(args.dataset),
        "summary": summarize(results),
        "cases": [result.to_dict() for result in results],
    }
    report = render_report(args.prompt_version, results)

    if args.compare_provider or args.compare_prompt_file:
        compare_kind = args.compare_provider or args.provider
        compare_addendum = (
            _addendum(args.compare_prompt_file) if args.compare_prompt_file else addendum
        )
        compared = await run_cases(
            cases,
            _provider(
                compare_kind,
                cases,
                args.compare_model or args.model,
                args.compare_base_url or args.base_url,
                args.compare_api_key or args.api_key,
                compare_addendum,
            ),
            prompt_version="comparison",
            prompt_addendum=compare_addendum,
        )
        payload["comparison"] = {
            "summary": summarize(compared),
            "cases": [item.to_dict() for item in compared],
        }
        report += "\n" + render_report("comparison", compared)

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.output_report.write_text(report, encoding="utf-8")
    summary = payload["summary"]
    assert isinstance(summary, dict)
    failed = summary["hard_failure_count"] or summary["pass_rate"] < args.min_pass_rate
    return 1 if failed else 0


def main() -> int:
    try:
        return asyncio.run(_run(_parse_args()))
    except EvaluationError as exc:
        print(f"Eval configuration error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
