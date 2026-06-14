"""RAG document models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Document:
    """A user knowledge-base document."""

    user_id: int
    content: str
    created_at: datetime
    title: str | None = None
    id: int | None = None


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    """A chunk of a document with optional embedding."""

    document_id: int
    chunk_index: int
    content: str
    embedding: bytes | None = None
    id: int | None = None
