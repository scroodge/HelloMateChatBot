"""Phase 24C decision-gate criteria tests."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from app.services.model_decision_service import ModelDecisionService


class FakeReports:
    def __init__(self) -> None:
        self.saved: list[object] = []

    def create(self, criteria_version: str, report: dict[str, object]) -> object:
        saved = SimpleNamespace(
            id=len(self.saved) + 1,
            criteria_version=criteria_version,
            report=report,
            created_at=datetime.now().astimezone(),
        )
        self.saved.append(saved)
        return saved

    def recent(self, *, limit: int = 10) -> list[object]:
        return self.saved[:limit]


class FakeCandidates:
    def matrix(self) -> list[dict[str, object]]:
        return [
            {
                "id": "candidate-gpt5", "name": "GPT-5 mini", "provider": "openai",
                "model": "gpt-5-mini", "status": "passed", "pass_rate": 1.0,
                "hard_failure_count": 0, "p95_latency_ms": 900,
                "mean_latency_ms": 500, "input_tokens": 10, "output_tokens": 5,
            }
        ]


class FakeReviews:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def recent(self, *, limit: int = 50) -> list[object]:
        return self.rows[:limit]


def _review(winner: str, mapping: str) -> object:
    return SimpleNamespace(
        candidate_id="candidate-gpt5", status="resolved", winner=winner, mapping=mapping
    )


def test_decision_gate_requires_enough_blind_reviews() -> None:
    service = ModelDecisionService(
        FakeReports(), FakeCandidates(), FakeReviews([_review("b", "b=baseline")])
    )

    row = service.create_report()["report"]["candidates"][0]

    assert row["safety_passed"] is True
    assert row["recommendation"] == "needs_owner_review"


def test_decision_gate_marks_safe_preferred_fast_candidate_eligible() -> None:
    reviews = [_review("b", "a=baseline") for _ in range(5)]
    service = ModelDecisionService(FakeReports(), FakeCandidates(), FakeReviews(reviews))

    row = service.create_report()["report"]["candidates"][0]

    assert row["candidate_wins"] == 5
    assert row["candidate_preference"] == 1.0
    assert row["recommendation"] == "eligible_for_owner_decision"
