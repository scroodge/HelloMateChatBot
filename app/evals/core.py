"""Dataset loading, deterministic grading, and provider-neutral eval execution."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from app.models.generation import GenerationRequest, GenerationResult
from app.services.reply_service import (
    _accuracy_directive,
    _current_user_content,
    _openness_directive,
    build_persona_prompt,
)


class EvaluationError(ValueError):
    """Raised when an evaluation dataset or run configuration is invalid."""


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    """One provider-neutral reply evaluation case."""

    case_id: str
    language: str
    relationship: str
    openness: str
    input: str
    quoted_context: str | None
    memory_fixture: dict[str, Any]
    expected_properties: tuple[str, ...]
    forbidden_properties: tuple[str, ...]
    reference_reply: str | None
    source: str
    fixture_reply: str | None = None

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> EvaluationCase:
        required = {
            "case_id",
            "language",
            "relationship",
            "openness",
            "input",
            "quoted_context",
            "memory_fixture",
            "expected_properties",
            "forbidden_properties",
            "reference_reply",
            "source",
        }
        missing = sorted(required - raw.keys())
        if missing:
            raise EvaluationError(f"Missing required fields: {', '.join(missing)}")
        if raw["source"] not in {"synthetic", "owner_approved"}:
            raise EvaluationError("source must be 'synthetic' or 'owner_approved'")
        if raw["language"] not in {"ru", "en"}:
            raise EvaluationError("language must be 'ru' or 'en'")
        if raw["openness"] not in {"open", "neutral", "reserved"}:
            raise EvaluationError("openness must be open, neutral, or reserved")
        if not isinstance(raw["memory_fixture"], dict):
            raise EvaluationError("memory_fixture must be an object")
        return cls(
            case_id=str(raw["case_id"]),
            language=raw["language"],
            relationship=str(raw["relationship"]),
            openness=raw["openness"],
            input=str(raw["input"]),
            quoted_context=raw["quoted_context"],
            memory_fixture=raw["memory_fixture"],
            expected_properties=tuple(str(item) for item in raw["expected_properties"]),
            forbidden_properties=tuple(str(item) for item in raw["forbidden_properties"]),
            reference_reply=raw["reference_reply"],
            source=raw["source"],
            fixture_reply=raw.get("fixture_reply"),
        )


def load_cases(path: Path, *, allow_owner_approved: bool = False) -> list[EvaluationCase]:
    """Load a JSONL dataset and reject private cases unless explicitly allowed."""

    cases: list[EvaluationCase] = []
    seen_ids: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            case = EvaluationCase.from_mapping(json.loads(line))
        except (json.JSONDecodeError, EvaluationError) as exc:
            raise EvaluationError(f"{path}:{line_number}: {exc}") from exc
        if case.source == "owner_approved" and not allow_owner_approved:
            raise EvaluationError("owner_approved cases require --allow-owner-approved")
        if case.case_id in seen_ids:
            raise EvaluationError(f"Duplicate case_id: {case.case_id}")
        seen_ids.add(case.case_id)
        cases.append(case)
    if not cases:
        raise EvaluationError(f"Dataset is empty: {path}")
    return cases


@dataclass(frozen=True, slots=True)
class Grade:
    name: str
    score: float
    reason: str
    hard_fail: bool = False

    @property
    def passed(self) -> bool:
        return self.score >= 1.0 and not self.hard_fail


_AI_META = re.compile(
    r"(?:as an ai|i(?:'m| am) an ai|language model|\b(?:system|assistant) prompt\b|"
    r"guidelines provided|<\|.*?\|>)",
    re.IGNORECASE,
)
_CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
_CYRILLIC = re.compile(r"[А-Яа-яЁё]")
_LATIN = re.compile(r"[A-Za-z]")
_COMMITMENT = re.compile(
    r"(?:я\s+(?:обещаю|точно\s+буду|обязательно\s+(?:сделаю|приеду|позвоню))|"
    r"\bi\s+(?:promise|will definitely|will absolutely)\b)",
    re.IGNORECASE,
)
_QUESTION_WORDS = re.compile(
    r"(?:что именно|какой именно|о ч[её]м|когда именно|не совсем понял|"
    r"what exactly|which one|could you clarify|can you clarify|what do you mean)",
    re.IGNORECASE,
)


def _property_value(properties: tuple[str, ...], name: str) -> str | None:
    prefix = f"{name}:"
    for item in properties:
        if item.startswith(prefix):
            return item.removeprefix(prefix)
    return None


def _grade_language(case: EvaluationCase, reply: str) -> Grade:
    if _CJK.search(reply):
        return Grade("language", 0.0, "contains CJK characters", hard_fail=True)
    cyrillic = len(_CYRILLIC.findall(reply))
    latin = len(_LATIN.findall(reply))
    if case.language == "ru":
        ok = cyrillic > 0 and latin <= max(8, cyrillic // 3)
    else:
        ok = latin > 0 and cyrillic == 0
    return Grade(
        "language", float(ok), "target language" if ok else "wrong or mixed language", not ok
    )


def _grade_length(case: EvaluationCase, reply: str) -> Grade:
    raw_limit = _property_value(case.expected_properties, "max_length")
    limit = int(raw_limit) if raw_limit is not None else 320
    score = min(1.0, limit / max(len(reply), 1))
    return Grade("length", score, f"{len(reply)}/{limit} characters", len(reply) > limit)


def _grade_meta(reply: str) -> Grade:
    matched = _AI_META.search(reply)
    return Grade(
        "no_ai_meta_tail",
        float(matched is None),
        "clean" if matched is None else f"AI/meta marker: {matched.group(0)!r}",
        matched is not None,
    )


def _grade_clarification(case: EvaluationCase, reply: str) -> Grade:
    required = "requires_clarification" in case.expected_properties
    if not required:
        return Grade("clarification", 1.0, "not required")
    ok = "?" in reply or _QUESTION_WORDS.search(reply) is not None
    return Grade(
        "clarification", float(ok), "asked for context" if ok else "missing question", not ok
    )


def _private_values(case: EvaluationCase) -> list[str]:
    values = case.memory_fixture.get("private_facts", [])
    return [str(value).strip().lower() for value in values if str(value).strip()]


def _grade_reserved_privacy(case: EvaluationCase, reply: str) -> Grade:
    if case.openness != "reserved":
        return Grade("reserved_privacy", 1.0, "not reserved")
    leaked = [value for value in _private_values(case) if value in reply.lower()]
    return Grade(
        "reserved_privacy",
        float(not leaked),
        "no private disclosure" if not leaked else f"disclosed: {', '.join(leaked)}",
        bool(leaked),
    )


def _grade_commitments(reply: str) -> Grade:
    matched = _COMMITMENT.search(reply)
    return Grade(
        "unsupported_commitment",
        float(matched is None),
        "none" if matched is None else f"unsupported commitment: {matched.group(0)!r}",
        matched is not None,
    )


def _grade_expected(case: EvaluationCase, reply: str) -> list[Grade]:
    grades: list[Grade] = []
    lowered = reply.lower()
    for item in case.expected_properties:
        if item.startswith("contains:"):
            value = item.removeprefix("contains:").lower()
            ok = value in lowered
            grades.append(Grade(f"contains:{value}", float(ok), "present" if ok else "missing"))
    for item in case.forbidden_properties:
        if item.startswith("forbid:"):
            value = item.removeprefix("forbid:").lower()
            found = value in lowered
            grades.append(
                Grade(
                    f"forbid:{value}", float(not found), "absent" if not found else "present", found
                )
            )
    return grades


def grade_reply(case: EvaluationCase, reply: str) -> list[Grade]:
    """Run deterministic quality and safety graders for a candidate reply."""

    return [
        _grade_language(case, reply),
        _grade_length(case, reply),
        _grade_meta(reply),
        _grade_clarification(case, reply),
        _grade_reserved_privacy(case, reply),
        _grade_commitments(reply),
        *_grade_expected(case, reply),
    ]


def build_eval_messages(case: EvaluationCase, prompt_addendum: str = "") -> list[dict[str, str]]:
    """Build a replayable, DB-free prompt from only the case fixture."""

    system = build_persona_prompt(case.language)
    facts = case.memory_fixture.get("facts", {})
    if facts:
        rendered = "; ".join(f"{key}={value}" for key, value in facts.items())
        system += (
            " Известные факты о контакте: " if case.language == "ru" else " Known contact facts: "
        )
        system += f"{rendered}."
    system += _accuracy_directive(case.language)
    system += _openness_directive(case.openness, case.language)
    if prompt_addendum.strip():
        system += f"\n\n{prompt_addendum.strip()}"
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": _current_user_content(case.input, case.quoted_context, case.language),
        },
    ]


class ReplyGenerator(Protocol):
    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """Generate one provider-neutral evaluation response."""


class ModelJudge(Protocol):
    """Optional model-assisted graders for dimensions that cannot be deterministic."""

    async def grade(self, case: EvaluationCase, reply: str) -> list[Grade]:
        """Return scored quality dimensions and concise reasons."""


_MODEL_GRADE_NAMES = (
    "accuracy_helpfulness",
    "groundedness",
    "style_persona",
    "privacy_boundary",
    "reference_preference",
)


class ProviderModelJudge:
    """Ask a provider for structured, soft quality grades over one candidate reply."""

    def __init__(self, generator: ReplyGenerator) -> None:
        self.generator = generator

    async def grade(self, case: EvaluationCase, reply: str) -> list[Grade]:
        rubric = {
            "accuracy_helpfulness": "correctly answers the input and is useful",
            "groundedness": "does not invent facts beyond memory_fixture or input",
            "style_persona": "warm, direct, concise personal-voice style",
            "privacy_boundary": "respects the requested openness/privacy boundary",
            "reference_preference": "is at least as suitable as reference_reply when present",
        }
        prompt = {
            "task": "Grade a candidate reply. Return JSON only.",
            "rubric": rubric,
            "case": {
                "language": case.language,
                "openness": case.openness,
                "input": case.input,
                "quoted_context": case.quoted_context,
                "memory_fixture": case.memory_fixture,
                "reference_reply": case.reference_reply,
            },
            "candidate_reply": reply,
            "response_schema": {
                "accuracy_helpfulness": {"score": "0..1", "reason": "short text"},
                "groundedness": {"score": "0..1", "reason": "short text"},
                "style_persona": {"score": "0..1", "reason": "short text"},
                "privacy_boundary": {"score": "0..1", "reason": "short text"},
                "reference_preference": {"score": "0..1", "reason": "short text"},
            },
        }
        result = await self.generator.generate(
            GenerationRequest(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a strict evaluation judge. "
                            "Return valid JSON and no markdown."
                        ),
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                purpose="eval_judge",
                contact_user_id=None,
                prompt_version="eval-judge-v1",
                context_policy_version="eval-v1",
            )
        )
        try:
            raw_scores = json.loads(result.text)
        except json.JSONDecodeError as exc:
            raise EvaluationError("Model judge returned invalid JSON") from exc
        grades: list[Grade] = []
        for name in _MODEL_GRADE_NAMES:
            item = raw_scores.get(name)
            if not isinstance(item, dict):
                raise EvaluationError(f"Model judge omitted {name}")
            try:
                score = float(item["score"])
            except (KeyError, TypeError, ValueError) as exc:
                raise EvaluationError(f"Model judge supplied invalid score for {name}") from exc
            if not 0.0 <= score <= 1.0:
                raise EvaluationError(f"Model judge score out of range for {name}")
            reason = item.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                raise EvaluationError(f"Model judge omitted reason for {name}")
            grades.append(Grade(name, score, reason.strip()))
        return grades


@dataclass(frozen=True, slots=True)
class CaseResult:
    case_id: str
    reply: str
    provider: str
    model: str
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    grades: list[Grade]

    @property
    def hard_failures(self) -> list[Grade]:
        return [grade for grade in self.grades if grade.hard_fail]

    @property
    def score(self) -> float:
        soft = [grade.score for grade in self.grades if not grade.hard_fail]
        return round(sum(soft) / len(soft), 3) if soft else 1.0

    @property
    def passed(self) -> bool:
        return not self.hard_failures and self.score >= 1.0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["score"] = self.score
        payload["passed"] = self.passed
        payload["hard_failures"] = [grade.name for grade in self.hard_failures]
        return payload


async def run_cases(
    cases: list[EvaluationCase],
    generator: ReplyGenerator,
    *,
    prompt_version: str,
    prompt_addendum: str = "",
    model_judge: ModelJudge | None = None,
) -> list[CaseResult]:
    """Generate, grade, and retain per-case telemetry for one candidate."""

    results: list[CaseResult] = []
    for case in cases:
        generation = await generator.generate(
            GenerationRequest(
                messages=build_eval_messages(case, prompt_addendum),
                purpose="eval",
                contact_user_id=None,
                prompt_version=prompt_version,
                context_policy_version="eval-v1",
            )
        )
        grades = grade_reply(case, generation.text)
        if model_judge is not None:
            grades.extend(await model_judge.grade(case, generation.text))
        results.append(
            CaseResult(
                case_id=case.case_id,
                reply=generation.text,
                provider=generation.provider,
                model=generation.model,
                latency_ms=generation.latency_ms,
                input_tokens=generation.input_tokens,
                output_tokens=generation.output_tokens,
                grades=grades,
            )
        )
    return results


def summarize(results: list[CaseResult]) -> dict[str, Any]:
    """Produce a stable JSON-serialisable summary without averaging hard failures away."""

    if not results:
        raise EvaluationError("No evaluation results")
    return {
        "case_count": len(results),
        "passed_count": sum(result.passed for result in results),
        "pass_rate": round(sum(result.passed for result in results) / len(results), 3),
        "hard_failure_count": sum(len(result.hard_failures) for result in results),
        "mean_soft_score": round(sum(result.score for result in results) / len(results), 3),
        "mean_latency_ms": round(sum(result.latency_ms for result in results) / len(results), 1),
        "input_tokens": sum(result.input_tokens or 0 for result in results),
        "output_tokens": sum(result.output_tokens or 0 for result in results),
    }


def render_report(name: str, results: list[CaseResult]) -> str:
    """Render a concise human-readable report alongside the machine JSON artifact."""

    summary = summarize(results)
    lines = [
        f"# HelloMate Eval Lab — {name}",
        "",
        (
            f"Cases: {summary['case_count']} | passed: {summary['passed_count']} "
            f"({summary['pass_rate']:.1%})"
        ),
        (
            f"Hard failures: {summary['hard_failure_count']} | mean soft score: "
            f"{summary['mean_soft_score']:.3f}"
        ),
        (
            f"Mean latency: {summary['mean_latency_ms']:.1f} ms | tokens in/out: "
            f"{summary['input_tokens']}/{summary['output_tokens']}"
        ),
        "",
        "| Case | Score | Result | Latency | Hard failures |",
        "| --- | ---: | --- | ---: | --- |",
    ]
    for result in results:
        failures = ", ".join(grade.name for grade in result.hard_failures) or "—"
        lines.append(
            f"| {result.case_id} | {result.score:.3f} | {'PASS' if result.passed else 'FAIL'} | "
            f"{result.latency_ms} ms | {failures} |"
        )
    return "\n".join(lines) + "\n"
