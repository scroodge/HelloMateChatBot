"""Debounce rapid-fire contact messages before generating a reply."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

FlushCallback = Callable[[str, str | None], Awaitable[None]]


@dataclass
class _PendingPart:
    text: str
    reply_context: str | None = None


@dataclass
class _PendingBuffer:
    parts: list[_PendingPart] = field(default_factory=list)
    on_flush: FlushCallback | None = None
    task: asyncio.Task[None] | None = None


class ReplyDebounceService:
    """Wait for a quiet period, then reply once to batched contact messages."""

    def __init__(self, delay_seconds: float) -> None:
        self.delay_seconds = delay_seconds
        self._buffers: dict[int, _PendingBuffer] = {}

    @property
    def enabled(self) -> bool:
        return self.delay_seconds > 0

    async def enqueue(
        self,
        contact_user_id: int,
        message_text: str,
        *,
        reply_context: str | None = None,
        on_flush: FlushCallback,
    ) -> None:
        """Buffer a message and (re)start the debounce timer."""

        if not message_text.strip():
            return

        buffer = self._buffers.get(contact_user_id)
        if buffer is None:
            buffer = _PendingBuffer()
            self._buffers[contact_user_id] = buffer

        buffer.parts.append(
            _PendingPart(
                text=message_text.strip(),
                reply_context=(reply_context or "").strip() or None,
            )
        )
        buffer.on_flush = on_flush

        if buffer.task is not None:
            buffer.task.cancel()

        buffer.task = asyncio.create_task(
            self._wait_and_flush(contact_user_id),
            name=f"reply-debounce-{contact_user_id}",
        )

    async def flush_now(self, contact_user_id: int) -> None:
        """Flush pending messages immediately without waiting."""

        await self._flush(contact_user_id)

    async def _wait_and_flush(self, contact_user_id: int) -> None:
        try:
            await asyncio.sleep(self.delay_seconds)
            await self._flush(contact_user_id)
        except asyncio.CancelledError:
            return

    async def _flush(self, contact_user_id: int) -> None:
        buffer = self._buffers.pop(contact_user_id, None)
        if buffer is None:
            return

        # Cancel the pending timer task — but NOT when _flush is running *inside*
        # that same task (the timer fired and called us). Cancelling self would
        # raise CancelledError on the first await in on_flush and silently abort
        # the whole reply pipeline (the suggest-mode "no draft" bug).
        current = asyncio.current_task()
        if buffer.task is not None and buffer.task is not current and not buffer.task.done():
            buffer.task.cancel()

        if not buffer.parts or buffer.on_flush is None:
            return

        combined = "\n".join(part.text for part in buffer.parts)
        quote_blocks = [
            f"Для сообщения «{part.text}»:\n{part.reply_context}"
            for part in buffer.parts
            if part.reply_context
        ]
        combined_reply_context = "\n\n".join(quote_blocks) or None
        # INFO when several messages were coalesced so batching is visible in prod
        # logs; DEBUG for the common single-message case to avoid noise.
        log = logger.info if len(buffer.parts) > 1 else logger.debug
        log(
            "Debounced reply for contact %s (%d parts): %r",
            contact_user_id,
            len(buffer.parts),
            combined[:120],
        )
        try:
            await buffer.on_flush(combined, combined_reply_context)
        except Exception:
            logger.exception("Debounced flush failed for contact %s", contact_user_id)
