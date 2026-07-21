"""Live status for contact reply generation.

The Telegram bot and the Mini App API run in the same process, but on different
threads. This registry deliberately keeps only transient state: durable drafts
remain in the suggestions table and disappear from the registry once complete.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from threading import RLock
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class ProcessingStatus:
    user_id: int
    message: str
    status: str  # queued | generating | failed
    updated_at: datetime
    error: str | None = None
    token: str = ""

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload.pop("token", None)
        payload["updated_at"] = self.updated_at.isoformat()
        return payload


class ProcessingStatusService:
    """Thread-safe registry of currently queued or generating contact replies."""

    def __init__(self) -> None:
        self._items: dict[int, ProcessingStatus] = {}
        self._lock = RLock()

    def begin(self, user_id: int, message: str) -> str:
        token = uuid4().hex
        with self._lock:
            self._items[user_id] = ProcessingStatus(
                user_id=user_id,
                message=message[:2000],
                status="queued",
                updated_at=datetime.now().astimezone(),
                token=token,
            )
        return token

    def set_generating(self, user_id: int, token: str) -> bool:
        return self._set(user_id, token, "generating")

    def set_failed(self, user_id: int, token: str, error: str) -> bool:
        with self._lock:
            current = self._items.get(user_id)
            if current is None or current.token != token:
                return False
            self._items[user_id] = ProcessingStatus(
                user_id=user_id,
                message=current.message,
                status="failed",
                updated_at=datetime.now().astimezone(),
                error=error[:200],
                token=token,
            )
            return True

    def clear(self, user_id: int, token: str) -> None:
        with self._lock:
            current = self._items.get(user_id)
            if current is not None and current.token == token:
                self._items.pop(user_id, None)

    def get(self, user_id: int) -> ProcessingStatus | None:
        with self._lock:
            return self._items.get(user_id)

    def list(self) -> list[ProcessingStatus]:
        with self._lock:
            return list(self._items.values())

    def _set(self, user_id: int, token: str, status: str) -> bool:
        with self._lock:
            current = self._items.get(user_id)
            if current is None or current.token != token:
                return False
            self._items[user_id] = ProcessingStatus(
                user_id=user_id,
                message=current.message,
                status=status,
                updated_at=datetime.now().astimezone(),
                token=token,
            )
            return True
