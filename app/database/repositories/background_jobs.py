"""Persistence primitives for the single-server durable worker."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.database.schema import background_jobs
from app.models.background_job import BackgroundJob

if TYPE_CHECKING:
    from app.database.db import Database


class BackgroundJobsRepository(Protocol):
    def enqueue(
        self,
        job_type: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
        max_attempts: int = 3,
        run_after: datetime | None = None,
    ) -> BackgroundJob: ...

    def claim_next(self, worker_id: str, *, lease_seconds: int) -> BackgroundJob | None: ...

    def complete(self, job_id: int, worker_id: str) -> bool: ...

    def retry_or_dead_letter(
        self, job_id: int, worker_id: str, error: str, *, run_after: datetime
    ) -> BackgroundJob | None: ...

    def stats(self) -> dict[str, int]: ...


class BackgroundJobsRepositoryImpl(BackgroundJobsRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    def enqueue(
        self,
        job_type: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
        max_attempts: int = 3,
        run_after: datetime | None = None,
    ) -> BackgroundJob:
        if not job_type.strip() or not idempotency_key.strip():
            raise ValueError("job_type and idempotency_key are required")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")

        now = datetime.now().astimezone()
        values = {
            "job_type": job_type.strip(),
            "payload": json.dumps(payload, ensure_ascii=False),
            "idempotency_key": idempotency_key.strip(),
            "status": "pending",
            "attempts": 0,
            "max_attempts": max_attempts,
            "run_after": (run_after or now).isoformat(),
            "lease_owner": None,
            "lease_expires_at": None,
            "last_error": None,
            "created_at": now.isoformat(),
            "started_at": None,
            "completed_at": None,
        }
        try:
            with self._db.engine.begin() as conn:
                result = conn.execute(background_jobs.insert().values(**values))
                job_id = int(result.inserted_primary_key[0])
        except IntegrityError:
            existing = self.get_by_idempotency_key(idempotency_key)
            if existing is not None:
                return existing
            raise
        job = self.get(job_id)
        assert job is not None
        return job

    def get(self, job_id: int) -> BackgroundJob | None:
        with self._db.engine.connect() as conn:
            row = conn.execute(
                select(background_jobs).where(background_jobs.c.id == job_id)
            ).first()
        return self._from_row(row) if row else None

    def get_by_idempotency_key(self, idempotency_key: str) -> BackgroundJob | None:
        with self._db.engine.connect() as conn:
            row = conn.execute(
                select(background_jobs).where(background_jobs.c.idempotency_key == idempotency_key)
            ).first()
        return self._from_row(row) if row else None

    def claim_next(self, worker_id: str, *, lease_seconds: int) -> BackgroundJob | None:
        if not worker_id.strip() or lease_seconds < 1:
            raise ValueError("worker_id and positive lease_seconds are required")
        now = datetime.now().astimezone()
        lease_expires_at = now + timedelta(seconds=lease_seconds)
        eligible = or_(
            and_(
                background_jobs.c.status == "pending",
                background_jobs.c.run_after <= now.isoformat(),
            ),
            and_(
                background_jobs.c.status == "running",
                background_jobs.c.lease_expires_at.is_not(None),
                background_jobs.c.lease_expires_at <= now.isoformat(),
            ),
        )
        with self._db.engine.begin() as conn:
            candidate = conn.execute(
                select(background_jobs.c.id)
                .where(eligible)
                .order_by(background_jobs.c.run_after, background_jobs.c.id)
                .limit(1)
            ).first()
            if candidate is None:
                return None
            result = conn.execute(
                update(background_jobs)
                .where(background_jobs.c.id == candidate.id, eligible)
                .values(
                    status="running",
                    attempts=background_jobs.c.attempts + 1,
                    lease_owner=worker_id.strip(),
                    lease_expires_at=lease_expires_at.isoformat(),
                    started_at=now.isoformat(),
                )
            )
            if result.rowcount != 1:
                return None
        return self.get(int(candidate.id))

    def complete(self, job_id: int, worker_id: str) -> bool:
        now = datetime.now().astimezone().isoformat()
        with self._db.engine.begin() as conn:
            result = conn.execute(
                update(background_jobs)
                .where(
                    background_jobs.c.id == job_id,
                    background_jobs.c.status == "running",
                    background_jobs.c.lease_owner == worker_id,
                )
                .values(
                    status="completed",
                    lease_owner=None,
                    lease_expires_at=None,
                    completed_at=now,
                )
            )
        return result.rowcount == 1

    def retry_or_dead_letter(
        self, job_id: int, worker_id: str, error: str, *, run_after: datetime
    ) -> BackgroundJob | None:
        job = self.get(job_id)
        if job is None or job.status != "running" or job.lease_owner != worker_id:
            return None
        is_dead = job.attempts >= job.max_attempts
        now = datetime.now().astimezone().isoformat()
        with self._db.engine.begin() as conn:
            result = conn.execute(
                update(background_jobs)
                .where(
                    background_jobs.c.id == job_id,
                    background_jobs.c.status == "running",
                    background_jobs.c.lease_owner == worker_id,
                )
                .values(
                    status="dead" if is_dead else "pending",
                    run_after=run_after.isoformat(),
                    lease_owner=None,
                    lease_expires_at=None,
                    last_error=error[:2000],
                    completed_at=now if is_dead else None,
                )
            )
        return self.get(job_id) if result.rowcount == 1 else None

    def stats(self) -> dict[str, int]:
        with self._db.engine.connect() as conn:
            rows = conn.execute(
                select(background_jobs.c.status, func.count(background_jobs.c.id))
                .group_by(background_jobs.c.status)
            ).all()
        counts = {str(status): int(count) for status, count in rows}
        return {
            "pending": counts.get("pending", 0),
            "running": counts.get("running", 0),
            "completed": counts.get("completed", 0),
            "dead": counts.get("dead", 0),
        }

    @staticmethod
    def _from_row(row: object) -> BackgroundJob:
        return BackgroundJob(
            id=int(row.id),
            job_type=row.job_type,
            payload=json.loads(row.payload),
            idempotency_key=row.idempotency_key,
            status=row.status,
            attempts=int(row.attempts),
            max_attempts=int(row.max_attempts),
            run_after=datetime.fromisoformat(row.run_after),
            lease_owner=row.lease_owner,
            lease_expires_at=(
                datetime.fromisoformat(row.lease_expires_at) if row.lease_expires_at else None
            ),
            last_error=row.last_error,
            created_at=datetime.fromisoformat(row.created_at),
            started_at=datetime.fromisoformat(row.started_at) if row.started_at else None,
            completed_at=datetime.fromisoformat(row.completed_at) if row.completed_at else None,
        )
