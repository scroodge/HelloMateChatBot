"""Tests for RAG service."""

from __future__ import annotations

import pytest

from app.models.documents import Document, DocumentChunk
from app.services.rag_service import RAGService


class InMemoryDocumentRepository:
    def __init__(self) -> None:
        self.documents: list[Document] = []
        self.chunks: list[DocumentChunk] = []
        self._document_id = 1
        self._chunk_id = 1

    def add_document(self, document: Document) -> Document:
        stored = Document(
            id=self._document_id,
            user_id=document.user_id,
            title=document.title,
            content=document.content,
            created_at=document.created_at,
        )
        self._document_id += 1
        self.documents.append(stored)
        return stored

    def list_documents(self, user_id: int) -> list[Document]:
        return [document for document in self.documents if document.user_id == user_id]

    def add_chunk(self, chunk: DocumentChunk) -> DocumentChunk:
        stored = DocumentChunk(
            id=self._chunk_id,
            document_id=chunk.document_id,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            embedding=chunk.embedding,
        )
        self._chunk_id += 1
        self.chunks.append(stored)
        return stored

    def list_chunks(self, user_id: int) -> list[DocumentChunk]:
        document_ids = {document.id for document in self.list_documents(user_id)}
        return [chunk for chunk in self.chunks if chunk.document_id in document_ids]


class FakeEmbeddingService:
    async def embed(self, text: str) -> bytes:
        if "cat" in text.lower():
            return b"\x00\x00\x80?"  # 1.0
        return b"\x00\x00\x00\x00"  # 0.0


@pytest.mark.asyncio
async def test_remember_indexes_document_chunks() -> None:
    repository = InMemoryDocumentRepository()
    service = RAGService(repository, FakeEmbeddingService(), chunk_size=20, top_k=1)
    document = await service.remember(1, "I love cats and coffee")
    assert document.id == 1
    assert len(repository.chunks) >= 1


@pytest.mark.asyncio
async def test_retrieve_context_prefers_relevant_chunk() -> None:
    repository = InMemoryDocumentRepository()
    service = RAGService(repository, FakeEmbeddingService(), chunk_size=50, top_k=1)
    await service.remember(1, "I love cats")
    context = await service.retrieve_context(1, "Tell me about cats")
    assert "cats" in context.lower()
