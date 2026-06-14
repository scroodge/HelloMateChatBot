"""RAG knowledge-base service."""

from __future__ import annotations

from datetime import datetime

from app.database.repositories.documents import DocumentRepository
from app.models.documents import Document, DocumentChunk
from app.services.embedding_service import EmbeddingService, cosine_similarity


class RAGService:
    """Store documents, chunk them, and retrieve relevant context."""

    def __init__(
        self,
        repository: DocumentRepository,
        embedding_service: EmbeddingService,
        chunk_size: int = 500,
        top_k: int = 3,
    ) -> None:
        self.repository = repository
        self.embedding_service = embedding_service
        self.chunk_size = chunk_size
        self.top_k = top_k

    def _chunk_text(self, text: str) -> list[str]:
        chunks: list[str] = []
        start = 0
        while start < len(text):
            chunks.append(text[start : start + self.chunk_size].strip())
            start += self.chunk_size
        return [chunk for chunk in chunks if chunk]

    async def remember(self, user_id: int, content: str, title: str | None = None) -> Document:
        """Store a user note and index its chunks."""

        document = self.repository.add_document(
            Document(
                user_id=user_id,
                title=title,
                content=content,
                created_at=datetime.now().astimezone(),
            )
        )
        if document.id is None:
            raise RuntimeError("Document ID missing after insert.")

        for index, chunk_text in enumerate(self._chunk_text(content)):
            embedding = await self.embedding_service.embed(chunk_text)
            self.repository.add_chunk(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=chunk_text,
                    embedding=embedding,
                )
            )
        return document

    async def retrieve_context(self, user_id: int, query: str) -> str:
        """Return the most relevant chunks for a query."""

        query_embedding = await self.embedding_service.embed(query)
        chunks = self.repository.list_chunks(user_id)
        scored: list[tuple[float, str]] = []
        for chunk in chunks:
            if chunk.embedding is None:
                continue
            score = cosine_similarity(query_embedding, chunk.embedding)
            scored.append((score, chunk.content))
        scored.sort(key=lambda item: item[0], reverse=True)
        top_chunks = [content for _, content in scored[: self.top_k]]
        return "\n".join(top_chunks)
