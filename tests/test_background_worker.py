"""Tests for the single-process durable background worker."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.database.db import Database
from app.services.background_worker import BackgroundWorker


@pytest.mark.asyncio
async def test_worker_completes_claimed_job(tmp_path: Path) -> None:
    with Database(f"sqlite:///{tmp_path / 'worker.db'}") as database:
        job = database.background_jobs.enqueue(
            "candidate_evaluation",
            {"candidate_id": "candidate-1"},
            idempotency_key="candidate-evaluation:candidate-1:1",
        )
        handled: list[dict[str, object]] = []

        async def handle(payload: dict[str, object]) -> None:
            handled.append(payload)

        worker = BackgroundWorker(
            database.background_jobs,
            {"candidate_evaluation": handle},
            worker_id="test-worker",
        )

        assert await worker.run_once() is True
        saved = database.background_jobs.get(job.id)

    assert handled == [{"candidate_id": "candidate-1"}]
    assert saved is not None
    assert saved.status == "completed"


@pytest.mark.asyncio
async def test_worker_retries_handler_failure(tmp_path: Path) -> None:
    with Database(f"sqlite:///{tmp_path / 'worker-retry.db'}") as database:
        job = database.background_jobs.enqueue(
            "candidate_evaluation",
            {"candidate_id": "candidate-1"},
            idempotency_key="candidate-evaluation:candidate-1:1",
            max_attempts=2,
        )

        async def fail(_: dict[str, object]) -> None:
            raise RuntimeError("provider unavailable")

        worker = BackgroundWorker(
            database.background_jobs,
            {"candidate_evaluation": fail},
            worker_id="test-worker",
        )

        assert await worker.run_once() is True
        saved = database.background_jobs.get(job.id)

    assert saved is not None
    assert saved.status == "pending"
    assert saved.attempts == 1
    assert saved.last_error == "provider unavailable"
