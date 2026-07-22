"""Shared resilience primitives for LLM HTTP providers."""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta
from typing import Any

import httpx


class ProviderRequestError(RuntimeError):
    """A provider failure with retry semantics safe for callers to inspect."""

    def __init__(self, message: str, *, retryable: bool, status_code: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class ResilientHttpClient:
    """Reusable, bounded HTTP client with retry and circuit-breaker protection."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 60.0,
        max_concurrency: int = 4,
        max_retries: int = 1,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._client: httpx.AsyncClient | None = None
        self._consecutive_failures = 0
        self._open_until: datetime | None = None

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        self._raise_if_circuit_open()
        async with self._semaphore:
            for attempt in range(self._max_retries + 1):
                try:
                    response = await self._get_client().post(url, **kwargs)
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    error = self._from_status_error(exc)
                except httpx.RequestError as exc:
                    error = ProviderRequestError(
                        f"Provider request failed: {exc}", retryable=True
                    )
                else:
                    self._record_success()
                    return response

                self._record_failure(error)
                if not error.retryable or attempt == self._max_retries:
                    raise error from None
                await asyncio.sleep(self._retry_delay(attempt))

        raise AssertionError("HTTP retry loop exited unexpectedly")

    async def aclose(self) -> None:
        if self._client is None:
            return
        close = getattr(self._client, "aclose", None)
        if close is not None:
            await close()
        self._client = None

    def health(self) -> dict[str, object]:
        now = datetime.now().astimezone()
        is_open = self._open_until is not None and self._open_until > now
        return {
            "available": not is_open,
            "consecutive_failures": self._consecutive_failures,
            "circuit_open_until": self._open_until.isoformat() if is_open else None,
        }

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = httpx.Timeout(self._timeout_seconds, connect=min(self._timeout_seconds, 10.0))
            self._client = httpx.AsyncClient(timeout=timeout)
        return self._client

    def _raise_if_circuit_open(self) -> None:
        if self._open_until is None:
            return
        now = datetime.now().astimezone()
        if self._open_until <= now:
            self._open_until = None
            return
        raise ProviderRequestError(
            "Provider is temporarily unavailable after repeated failures.", retryable=True
        )

    @staticmethod
    def _from_status_error(exc: httpx.HTTPStatusError) -> ProviderRequestError:
        status_code = exc.response.status_code
        retryable = status_code in {408, 409, 425, 429} or status_code >= 500
        return ProviderRequestError(
            f"Provider returned HTTP {status_code}.",
            retryable=retryable,
            status_code=status_code,
        )

    def _record_success(self) -> None:
        self._consecutive_failures = 0
        self._open_until = None

    def _record_failure(self, error: ProviderRequestError) -> None:
        if not error.retryable:
            return
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._failure_threshold:
            self._open_until = datetime.now().astimezone() + timedelta(
                seconds=self._cooldown_seconds
            )

    @staticmethod
    def _retry_delay(attempt: int) -> float:
        return min(0.25 * 2**attempt, 2.0) + random.uniform(0, 0.1)
