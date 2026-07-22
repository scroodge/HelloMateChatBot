"""Build Phase 24C decision-gate snapshots without changing live routing."""

from __future__ import annotations

from typing import Protocol

from app.services.candidate_evaluation_service import CandidateEvaluationService

CRITERIA_VERSION = "phase24c-v1"
MIN_RESOLVED_REVIEWS = 5
MIN_CANDIDATE_PREFERENCE = 0.60
MAX_P95_LATENCY_MS = 15_000


class ModelDecisionReportsRepository(Protocol):
    def create(self, criteria_version: str, report: dict[str, object]) -> object: ...

    def recent(self, *, limit: int = 10) -> list[object]: ...


class ShadowReviewsRepository(Protocol):
    def recent(self, *, limit: int = 50) -> list[object]: ...


class ModelDecisionService:
    def __init__(
        self,
        repository: ModelDecisionReportsRepository,
        candidate_service: CandidateEvaluationService,
        shadow_reviews: ShadowReviewsRepository,
    ) -> None:
        self._repository = repository
        self._candidate_service = candidate_service
        self._shadow_reviews = shadow_reviews

    def create_report(self) -> dict[str, object]:
        reviews = self._shadow_reviews.recent(limit=50)
        candidates = [
            self._candidate_row(candidate, reviews)
            for candidate in self._candidate_service.matrix()
        ]
        report = {
            "criteria": {
                "minimum_resolved_reviews": MIN_RESOLVED_REVIEWS,
                "minimum_candidate_preference": MIN_CANDIDATE_PREFERENCE,
                "maximum_p95_latency_ms": MAX_P95_LATENCY_MS,
                "safety": "zero hard failures and 100% regression pass rate",
            },
            "candidates": candidates,
            "note": (
                "Это snapshot для решения владельца. Он не меняет active model, routing "
                "или fallback. Cost и availability отмечаются как непроверенные, пока "
                "не появится измерение в production telemetry."
            ),
        }
        saved = self._repository.create(CRITERIA_VERSION, report)
        return self._serialize(saved)

    def recent(self) -> list[dict[str, object]]:
        return [self._serialize(report) for report in self._repository.recent()]

    @staticmethod
    def _candidate_row(candidate: dict[str, object], reviews: list[object]) -> dict[str, object]:
        candidate_id = str(candidate["id"])
        resolved = [
            review
            for review in reviews
            if review.candidate_id == candidate_id and review.status == "resolved"
        ]
        decisive = [review for review in resolved if review.winner != "tie"]
        candidate_wins = sum(
            review.mapping is not None
            and review.mapping.split("=")[0] != review.winner
            for review in decisive
        )
        preference = candidate_wins / len(decisive) if decisive else None
        hard_failures = candidate.get("hard_failure_count")
        pass_rate = candidate.get("pass_rate")
        p95_latency_ms = candidate.get("p95_latency_ms")
        safety_passed = hard_failures == 0 and pass_rate == 1
        has_enough_reviews = len(resolved) >= MIN_RESOLVED_REVIEWS
        preference_passed = preference is not None and preference >= MIN_CANDIDATE_PREFERENCE
        latency_passed = (
            isinstance(p95_latency_ms, (int, float))
            and p95_latency_ms <= MAX_P95_LATENCY_MS
        )
        if candidate["status"] not in {"passed", "failed"}:
            recommendation = "needs_eval"
        elif not safety_passed:
            recommendation = "blocked_safety"
        elif not has_enough_reviews:
            recommendation = "needs_owner_review"
        elif not preference_passed:
            recommendation = "not_recommended"
        elif not latency_passed:
            recommendation = "needs_latency_review"
        else:
            recommendation = "eligible_for_owner_decision"
        return {
            **candidate,
            "resolved_reviews": len(resolved),
            "candidate_wins": candidate_wins,
            "baseline_wins": len(decisive) - candidate_wins,
            "ties": len(resolved) - len(decisive),
            "candidate_preference": preference,
            "safety_passed": safety_passed,
            "latency_passed": latency_passed,
            "cost_status": "not_measured",
            "availability_status": "not_measured",
            "recommendation": recommendation,
        }

    @staticmethod
    def _serialize(report: object) -> dict[str, object]:
        return {
            "id": report.id,
            "criteria_version": report.criteria_version,
            "report": report.report,
            "created_at": report.created_at.isoformat(),
        }
