"""Durable background job records (Phase 22A)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class BackgroundJob:
    id: int
    job_type: str
    payload: dict[str, Any]
    idempotency_key: str
    status: str
    attempts: int
    max_attempts: int
    run_after: datetime
    created_at: datetime
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    last_error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
