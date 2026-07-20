"""Tests for reply debounce service."""

from __future__ import annotations

import asyncio

import pytest

from app.services.reply_debounce_service import ReplyDebounceService


@pytest.mark.asyncio
async def test_debounce_batches_rapid_messages() -> None:
    service = ReplyDebounceService(delay_seconds=0.2)
    flushed: list[str] = []

    async def on_flush(text: str, reply_context: str | None) -> None:
        flushed.append(text)

    await service.enqueue(1, "пап", on_flush=on_flush)
    await service.enqueue(1, "разбуди", on_flush=on_flush)
    await service.enqueue(1, "в 7", on_flush=on_flush)

    await asyncio.sleep(0.35)

    assert flushed == ["пап\nразбуди\nв 7"]


@pytest.mark.asyncio
async def test_flush_now_skips_delay() -> None:
    service = ReplyDebounceService(delay_seconds=10)
    flushed: list[str] = []

    async def on_flush(text: str, reply_context: str | None) -> None:
        flushed.append(text)

    await service.enqueue(2, "привет", on_flush=on_flush)
    await service.flush_now(2)

    assert flushed == ["привет"]


@pytest.mark.asyncio
async def test_disabled_when_delay_zero() -> None:
    service = ReplyDebounceService(delay_seconds=0)
    assert service.enabled is False


@pytest.mark.asyncio
async def test_timer_flush_runs_on_flush_to_completion() -> None:
    """Regression: the timer-driven flush must not cancel itself.

    on_flush awaits (simulating the LLM/embed pipeline); a self-cancel in _flush
    would raise CancelledError on that await and silently abort, leaving the
    callback unfinished (the suggest-mode "no draft" bug).
    """
    service = ReplyDebounceService(delay_seconds=0.1)
    completed: list[str] = []

    async def on_flush(text: str, reply_context: str | None) -> None:
        await asyncio.sleep(0.05)  # force a real suspension point
        completed.append(text)

    await service.enqueue(1, "привет", on_flush=on_flush)
    await asyncio.sleep(0.3)

    assert completed == ["привет"]  # callback ran fully, was not cancelled


@pytest.mark.asyncio
async def test_debounce_preserves_quote_for_the_specific_message() -> None:
    service = ReplyDebounceService(delay_seconds=10)
    flushed: list[tuple[str, str | None]] = []

    async def on_flush(text: str, reply_context: str | None) -> None:
        flushed.append((text, reply_context))

    await service.enqueue(
        1,
        "Переведи)))",
        reply_context="Цитируемое сообщение (Я):\nбаланс так баланс",
        on_flush=on_flush,
    )
    await service.enqueue(1, "Я не поняла", on_flush=on_flush)
    await service.flush_now(1)

    assert flushed == [
        (
            "Переведи)))\nЯ не поняла",
            "Для сообщения «Переведи)))»:\n" "Цитируемое сообщение (Я):\nбаланс так баланс",
        )
    ]
