"""RAG document persistence repository."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import insert, select

from app.database.schema import document_chunks, documents
from app.models.documents import Document, DocumentChunk

if TYPE_CHECKING:
    from app.database.db import Database


class DocumentRepository(Protocol):
    """Persistence contract for user documents and chunks."""

    def add_document(self, document: Document) -> Document: ...

    def list_documents(self, user_id: int) -> list[Document]: ...

    def add_chunk(self, chunk: DocumentChunk) -> DocumentChunk: ...

    def list_chunks(self, user_id: int) -> list[DocumentChunk]: ...


class DocumentRepositoryImpl:
    """SQLAlchemy implementation of DocumentRepository."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def add_document(self, document: Document) -> Document:
        with self._db.engine.begin() as connection:
            result = connection.execute(
                insert(documents).values(
                    user_id=document.user_id,
                    title=document.title,
                    content=document.content,
                    created_at=document.created_at.isoformat(),
                )
            )
            document_id = int(result.inserted_primary_key[0])
        return Document(
            id=document_id,
            user_id=document.user_id,
            title=document.title,
            content=document.content,
            created_at=document.created_at,
        )

    def list_documents(self, user_id: int) -> list[Document]:
        with self._db.engine.connect() as connection:
            rows = connection.execute(
                select(documents)
                .where(documents.c.user_id == user_id)
                .order_by(documents.c.created_at.desc())
            ).all()
        return [
            Document(
                id=int(row.id),
                user_id=int(row.user_id),
                title=row.title,
                content=row.content,
                created_at=datetime.fromisoformat(row.created_at),
            )
            for row in rows
        ]

    def add_chunk(self, chunk: DocumentChunk) -> DocumentChunk:
        with self._db.engine.begin() as connection:
            result = connection.execute(
                insert(document_chunks).values(
                    document_id=chunk.document_id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    embedding=chunk.embedding,
                )
            )
            chunk_id = int(result.inserted_primary_key[0])
        return DocumentChunk(
            id=chunk_id,
            document_id=chunk.document_id,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            embedding=chunk.embedding,
        )

    def list_chunks(self, user_id: int) -> list[DocumentChunk]:
        with self._db.engine.connect() as connection:
            rows = connection.execute(
                select(document_chunks)
                .select_from(
                    document_chunks.join(documents, documents.c.id == document_chunks.c.document_id)
                )
                .where(documents.c.user_id == user_id)
                .order_by(document_chunks.c.id)
            ).all()
        return [
            DocumentChunk(
                id=int(row.id),
                document_id=int(row.document_id),
                chunk_index=int(row.chunk_index),
                content=row.content,
                embedding=row.embedding,
            )
            for row in rows
        ]
