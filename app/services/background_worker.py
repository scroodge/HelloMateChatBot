"""Single-process worker for durable background jobs."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from app.database.repositories.background_jobs import BackgroundJobsRepository
from app.models.background_job import BackgroundJob

logger = logging.getLogger(__name__)

JobHandler = Callable[[dict[str, Any]], Awaitable[None]]


class BackgroundWorker:
    """Claims one leased job at a time and records every terminal outcome."""

    def __init__(
        self,
        repository: BackgroundJobsRepository,
        handlers: dict[str, JobHandler],
        *,
        worker_id: str = "api-worker",
        poll_interval_seconds: float = 1.0,
        lease_seconds: int = 900,
    ) -> None:
        self._repository = repository
        self._handlers = handlers
        self._worker_id = worker_id
        self._poll_interval_seconds = poll_interval_seconds
        self._lease_seconds = lease_seconds
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop_event.clear()
            self._task = asyncio.create_task(self.run(), name=self._worker_id)

    def health(self) -> dict[str, object]:
        return {
            "worker_id": self._worker_id,
            "running": self._task is not None and not self._task.done(),
            "queue": self._repository.stats(),
        }

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            await self._task

    async def run(self) -> None:
        while not self._stop_event.is_set():
            did_process_job = await self.run_once()
            if not did_process_job:
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=self._poll_interval_seconds
                    )
                except TimeoutError:
                    pass

    async def run_once(self) -> bool:
        job = self._repository.claim_next(
            self._worker_id, lease_seconds=self._lease_seconds
        )
        if job is None:
            return False

        await self._handle(job)
        return True

    async def _handle(self, job: BackgroundJob) -> None:
        handler = self._handlers.get(job.job_type)
        if handler is None:
            self._dead_letter(job, f"No handler registered for {job.job_type!r}")
            return

        try:
            await handler(job.payload)
        except Exception as exc:  # job errors must become durable state
            logger.exception("Background job %s failed", job.id)
            self._retry(job, str(exc))
            return

        if not self._repository.complete(job.id, self._worker_id):
            logger.warning("Background job %s lease was lost before completion", job.id)

    def _retry(self, job: BackgroundJob, error: str) -> None:
        delay_seconds = min(30 * 2 ** max(job.attempts - 1, 0), 15 * 60)
        jitter_seconds = random.uniform(0, min(delay_seconds * 0.2, 30))
        self._repository.retry_or_dead_letter(
            job.id,
            self._worker_id,
            error,
            run_after=datetime.now().astimezone()
            + timedelta(seconds=delay_seconds + jitter_seconds),
        )

    def _dead_letter(self, job: BackgroundJob, error: str) -> None:
        self._repository.retry_or_dead_letter(
            job.id,
            self._worker_id,
            error,
            run_after=datetime.now().astimezone(),
        )
