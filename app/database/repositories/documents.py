"""RAG document persistence repository."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from app.models.documents import Document, DocumentChunk

if TYPE_CHECKING:
    from app.database.sqlite import SQLiteDatabase


class DocumentRepository(Protocol):
    """Persistence contract for user documents and chunks."""

    def add_document(self, document: Document) -> Document: ...

    def list_documents(self, user_id: int) -> list[Document]: ...

    def add_chunk(self, chunk: DocumentChunk) -> DocumentChunk: ...

    def list_chunks(self, user_id: int) -> list[DocumentChunk]: ...


class SQLiteDocumentRepository:
    """SQLite implementation of DocumentRepository."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def add_document(self, document: Document) -> Document:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO documents (user_id, title, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    document.user_id,
                    document.title,
                    document.content,
                    document.created_at.isoformat(),
                ),
            )
            document_id = int(cursor.lastrowid)
        return Document(
            id=document_id,
            user_id=document.user_id,
            title=document.title,
            content=document.content,
            created_at=document.created_at,
        )

    def list_documents(self, user_id: int) -> list[Document]:
        rows = self._database.connection.execute(
            """
            SELECT id, user_id, title, content, created_at
            FROM documents
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()
        return [
            Document(
                id=int(row["id"]),
                user_id=int(row["user_id"]),
                title=row["title"],
                content=row["content"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def add_chunk(self, chunk: DocumentChunk) -> DocumentChunk:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO document_chunks (document_id, chunk_index, content, embedding)
                VALUES (?, ?, ?, ?)
                """,
                (
                    chunk.document_id,
                    chunk.chunk_index,
                    chunk.content,
                    chunk.embedding,
                ),
            )
            chunk_id = int(cursor.lastrowid)
        return DocumentChunk(
            id=chunk_id,
            document_id=chunk.document_id,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            embedding=chunk.embedding,
        )

    def list_chunks(self, user_id: int) -> list[DocumentChunk]:
        rows = self._database.connection.execute(
            """
            SELECT c.id, c.document_id, c.chunk_index, c.content, c.embedding
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE d.user_id = ?
            ORDER BY c.id
            """,
            (user_id,),
        ).fetchall()
        return [
            DocumentChunk(
                id=int(row["id"]),
                document_id=int(row["document_id"]),
                chunk_index=int(row["chunk_index"]),
                content=row["content"],
                embedding=row["embedding"],
            )
            for row in rows
        ]
