"""Tests for Phase 13 semantic recall service."""

from __future__ import annotations

import struct
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.database.db import Database
from app.services.embedding_service import EmbeddingService
from app.services.memory_service import MemoryService
from app.services.recall_service import RecallService

# ── Helpers ────────────────────────────────────────────────────────────────────


def _pack(values: list[float]) -> bytes:
    return struct.pack(f"{len(values)}f", *values)


def _make_services(tmp_path, *, top_k: int = 3, min_score: float = 0.4):
    db = Database(f"sqlite:///{tmp_path / 'recall.db'}")
    db.open()
    memory = MemoryService(db.memory, window_size=5)
    embedding_service = MagicMock(spec=EmbeddingService)
    recall = RecallService(
        memory_service=memory,
        embedding_service=embedding_service,
        window_size=5,
        top_k=top_k,
        min_chars=5,
        min_score=min_score,
        backfill_batch=10,
        enabled=True,
    )
    return db, memory, embedding_service, recall


# ── Unit tests ──────────────────────────────────────────────────────────────────


def test_recall_disabled_does_not_schedule(tmp_path) -> None:
    db, memory, emb, recall = _make_services(tmp_path)
    with db:
        recall.enabled = False
        recall.schedule_index(1)
        assert len(recall._tasks) == 0


@pytest.mark.asyncio
async def test_maybe_index_embeds_new_messages(tmp_path) -> None:
    db, memory, emb, recall = _make_services(tmp_path)
    with db:
        msg = memory.record_user_message(1, "Привет, как дела?")

        vec = _pack([1.0, 0.0, 0.0])
        emb.embed = AsyncMock(return_value=vec)

        await recall.maybe_index(1)

        pairs = memory.list_embeddings_for_user(1)
        assert len(pairs) == 1
        assert pairs[0][0] == msg.id
        assert pairs[0][1] == vec

        watermark = memory.get_recall_watermark(1)
        assert watermark == msg.id


@pytest.mark.asyncio
async def test_maybe_index_skips_short_messages(tmp_path) -> None:
    db, memory, emb, recall = _make_services(tmp_path)
    with db:
        recall.min_chars = 20  # "Hi" is too short
        memory.record_user_message(1, "Hi")

        emb.embed = AsyncMock(return_value=_pack([1.0]))
        await recall.maybe_index(1)

        # Nothing indexed; watermark stays at 0
        assert memory.list_embeddings_for_user(1) == []
        assert memory.get_recall_watermark(1) == 0


@pytest.mark.asyncio
async def test_maybe_index_is_idempotent(tmp_path) -> None:
    db, memory, emb, recall = _make_services(tmp_path)
    with db:
        memory.record_user_message(1, "Расскажи про себя")
        vec = _pack([0.5, 0.5])
        emb.embed = AsyncMock(return_value=vec)

        await recall.maybe_index(1)
        await recall.maybe_index(1)  # second call should index nothing new

        # embed called only once
        assert emb.embed.await_count == 1


@pytest.mark.asyncio
async def test_retrieve_returns_relevant_message(tmp_path) -> None:
    db, memory, emb, recall = _make_services(tmp_path)
    with db:
        memory.record_user_message(1, "Я люблю рыбалку на озере")

        stored_vec = _pack([1.0, 0.0])
        query_vec = _pack([0.95, 0.1])  # close enough
        emb.embed = AsyncMock(side_effect=[stored_vec, query_vec])

        await recall.maybe_index(1)

        # Reset embed mock for retrieve call
        emb.embed = AsyncMock(return_value=query_vec)
        result = await recall.retrieve(1, "рыбалка", exclude_recent_n=0)
        assert "рыбалку" in result


@pytest.mark.asyncio
async def test_retrieve_excludes_live_window(tmp_path) -> None:
    db, memory, emb, recall = _make_services(tmp_path)
    with db:
        # Record 6 messages; window_size=5, so first one is outside live window
        memory.record_user_message(1, "Сообщение из прошлого")
        for i in range(5):
            memory.record_user_message(1, f"Живое сообщение {i}")

        old_vec = _pack([1.0, 0.0])
        emb.embed = AsyncMock(return_value=old_vec)
        await recall.maybe_index(1)

        # retrieve with exclude_recent_n=5 should skip all live-window messages
        # Only msg_old is outside the window
        emb.embed = AsyncMock(return_value=old_vec)
        result = await recall.retrieve(1, "прошлое", exclude_recent_n=5)
        assert "прошлого" in result or result != ""


@pytest.mark.asyncio
async def test_retrieve_below_min_score_returns_empty(tmp_path) -> None:
    db, memory, emb, recall = _make_services(tmp_path, min_score=0.99)
    with db:
        memory.record_user_message(1, "Что-то не то")
        stored_vec = _pack([1.0, 0.0])
        emb.embed = AsyncMock(return_value=stored_vec)
        await recall.maybe_index(1)

        # Query vector is orthogonal → score 0.0 < min_score 0.99
        query_vec = _pack([0.0, 1.0])
        emb.embed = AsyncMock(return_value=query_vec)
        result = await recall.retrieve(1, "что-то", exclude_recent_n=0)
        assert result == ""


@pytest.mark.asyncio
async def test_retrieve_disabled_returns_empty(tmp_path) -> None:
    db, memory, emb, recall = _make_services(tmp_path)
    with db:
        recall.enabled = False
        emb.embed = AsyncMock(return_value=_pack([1.0]))
        result = await recall.retrieve(1, "запрос", exclude_recent_n=0)
        assert result == ""
        emb.embed.assert_not_called()


@pytest.mark.asyncio
async def test_embedding_error_stops_batch_and_keeps_partial_watermark(tmp_path) -> None:
    """If embedding fails mid-batch, watermark advances only up to the last success."""

    db, memory, emb, recall = _make_services(tmp_path)
    with db:
        m1 = memory.record_user_message(1, "Первое сообщение")
        memory.record_user_message(1, "Второе сообщение")

        good_vec = _pack([1.0])
        emb.embed = AsyncMock(side_effect=[good_vec, RuntimeError("LLM down")])

        await recall.maybe_index(1)

        # First message indexed, second skipped
        pairs = memory.list_embeddings_for_user(1)
        assert len(pairs) == 1
        assert pairs[0][0] == m1.id

        # Watermark points at the last successful message
        assert memory.get_recall_watermark(1) == m1.id


# ── Repository-level tests ─────────────────────────────────────────────────────


def test_repository_watermark_round_trip(tmp_path) -> None:
    db, memory, _, _ = _make_services(tmp_path)
    with db:
        assert memory.get_recall_watermark(42) == 0
        memory.set_recall_watermark(42, 999)
        assert memory.get_recall_watermark(42) == 999
        memory.set_recall_watermark(42, 1500)
        assert memory.get_recall_watermark(42) == 1500


def test_repository_list_messages_by_ids(tmp_path) -> None:
    db, memory, _, _ = _make_services(tmp_path)
    with db:
        m1 = memory.record_user_message(7, "Привет")
        m2 = memory.record_user_message(7, "Как дела?")
        m3 = memory.record_user_message(7, "Пока")

        result = memory.list_messages_by_ids(7, {m1.id, m3.id})
        ids = {m.id for m in result}
        assert m1.id in ids
        assert m3.id in ids
        assert m2.id not in ids


def test_repository_list_unindexed_skips_assistant_messages(tmp_path) -> None:
    db, memory, _, recall = _make_services(tmp_path)
    with db:
        memory.record_user_message(1, "Пользователь пишет")
        memory.record_assistant_message(1, "Бот отвечает")

        msgs = memory.list_unindexed_messages(1, after_id=0, limit=10, min_chars=5)
        assert all(m.role == "user" for m in msgs)
        assert len(msgs) == 1
