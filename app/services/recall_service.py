"""Semantic recall via per-message embeddings (Phase 13).

Indexes contact messages as they arrive (lazy background) and retrieves the
most semantically similar past messages to enrich the reply context.  The
recall block is injected between the rolling summary and the live message
window so the LLM can reference things said weeks ago.

Design decisions (agreed 2026-06-14):
- Granularity: per message (not per conversation turn)
- Activation: always on (ignores openness/style settings)
- Backfill: lazy in the background using a per-user watermark
"""

from __future__ import annotations

import asyncio
import logging

from app.services.embedding_service import EmbeddingService, cosine_similarity
from app.services.memory_service import MemoryService

logger = logging.getLogger(__name__)


class RecallService:
    """Index and retrieve semantically relevant past messages per contact."""

    def __init__(
        self,
        *,
        memory_service: MemoryService,
        embedding_service: EmbeddingService,
        window_size: int,
        top_k: int,
        min_chars: int,
        min_score: float,
        backfill_batch: int,
        enabled: bool,
    ) -> None:
        self.memory_service = memory_service
        self.embedding_service = embedding_service
        self.window_size = window_size
        self.top_k = top_k
        self.min_chars = min_chars
        self.min_score = min_score
        self.backfill_batch = backfill_batch
        self.enabled = enabled
        self._in_progress: set[int] = set()
        self._tasks: set[asyncio.Task[None]] = set()

    def schedule_index(self, user_id: int) -> None:
        """Fire-and-forget: index new contact messages for user_id."""

        if not self.enabled:
            return
        try:
            task = asyncio.create_task(self.maybe_index(user_id))
        except RuntimeError:
            return
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def maybe_index(self, user_id: int) -> None:
        """Index unindexed contact messages up to backfill_batch at a time."""

        if not self.enabled or user_id in self._in_progress:
            return

        self._in_progress.add(user_id)
        try:
            watermark = self.memory_service.get_recall_watermark(user_id)
            messages = self.memory_service.list_unindexed_messages(
                user_id,
                after_id=watermark,
                limit=self.backfill_batch,
                min_chars=self.min_chars,
            )
            if not messages:
                return

            new_watermark = watermark
            for msg in messages:
                if msg.id is None:
                    continue
                try:
                    embedding = await self.embedding_service.embed(msg.content)
                    self.memory_service.add_message_embedding(msg.id, user_id, embedding)
                    new_watermark = max(new_watermark, msg.id)
                except Exception:
                    logger.exception("Failed to embed message %s for contact %s", msg.id, user_id)
                    break  # stop on first error; retry next time

            if new_watermark > watermark:
                self.memory_service.set_recall_watermark(user_id, new_watermark)
                logger.debug(
                    "Recall index updated for contact %s: watermark %d → %d (%d msgs)",
                    user_id,
                    watermark,
                    new_watermark,
                    len(messages),
                )
        except Exception:
            logger.exception("Failed to index recall for contact %s", user_id)
        finally:
            self._in_progress.discard(user_id)

    async def retrieve(
        self,
        user_id: int,
        query: str,
        exclude_recent_n: int = 0,
    ) -> str:
        """Return the most relevant past messages as a formatted string.

        Messages in the live window (most recent exclude_recent_n) are skipped
        because they are already present in the conversation history sent to the
        LLM.  Only messages above min_score are included.
        """

        if not self.enabled or not query:
            return ""

        try:
            query_embedding = await self.embedding_service.embed(query)
        except Exception:
            logger.exception("Failed to embed query for recall (contact %s)", user_id)
            return ""

        pairs = self.memory_service.list_embeddings_for_user(user_id)
        if not pairs:
            return ""

        # Determine the message_id cutoff so live-window messages are excluded.
        # list_unindexed_messages with limit=0 would be wrong; instead we find
        # the id of the (exclude_recent_n+1)-th message from the end.
        cutoff_id = self._live_window_cutoff(user_id, exclude_recent_n)

        scored: list[tuple[float, int]] = []
        for message_id, embedding in pairs:
            if cutoff_id is not None and message_id >= cutoff_id:
                continue  # skip live window
            score = cosine_similarity(query_embedding, embedding)
            if score >= self.min_score:
                scored.append((score, message_id))

        if not scored:
            return ""

        scored.sort(reverse=True)
        top_ids = {message_id for _, message_id in scored[: self.top_k]}

        # Fetch the actual text for top hits in one shot.
        messages = self.memory_service.list_messages_by_ids(user_id, top_ids)
        if not messages:
            return ""

        # Sort by message_id ascending so the context reads chronologically.
        messages.sort(key=lambda m: m.id or 0)
        return " | ".join(m.content for m in messages)

    def _live_window_cutoff(self, user_id: int, exclude_recent_n: int) -> int | None:
        """Return the minimum message_id of the live window, or None if not applicable."""

        if exclude_recent_n <= 0:
            return None
        total = self.memory_service.count_messages(user_id)
        if total <= exclude_recent_n:
            return None  # all messages are in the live window
        offset = total - exclude_recent_n
        boundary = self.memory_service.messages_slice(user_id, offset=offset, limit=1)
        if not boundary:
            return None
        return boundary[0].id
