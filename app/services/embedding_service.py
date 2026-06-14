"""Embedding generation for RAG."""

from __future__ import annotations

import math
import struct

import httpx


class EmbeddingService:
    """Generate embeddings via Ollama or a compatible API."""

    def __init__(
        self,
        base_url: str,
        model: str = "nomic-embed-text",
        api_key: str = "",
        provider: str = "ollama",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.provider = provider

    async def embed(self, text: str) -> bytes:
        """Return a float vector serialized as bytes."""

        if self.provider == "openai":
            return await self._embed_openai(text)
        return await self._embed_ollama(text)

    async def _embed_ollama(self, text: str) -> bytes:
        payload = {"model": self.model, "prompt": text}
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(f"{self.base_url}/api/embeddings", json=payload)
            response.raise_for_status()
            data = response.json()
        embedding = data.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            raise RuntimeError("Ollama returned an empty embedding.")
        return _pack_embedding(embedding)

    async def _embed_openai(self, text: str) -> bytes:
        if not self.api_key:
            raise RuntimeError("LLM_API_KEY is required for OpenAI embeddings.")
        payload = {"model": self.model, "input": text}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/v1/embeddings",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
        items = data.get("data", [])
        if not items:
            raise RuntimeError("OpenAI embeddings API returned no data.")
        embedding = items[0].get("embedding")
        if not isinstance(embedding, list) or not embedding:
            raise RuntimeError("OpenAI returned an empty embedding.")
        return _pack_embedding(embedding)


def _pack_embedding(values: list[float]) -> bytes:
    return struct.pack(f"{len(values)}f", *[float(value) for value in values])


def _unpack_embedding(blob: bytes) -> list[float]:
    count = len(blob) // 4
    return list(struct.unpack(f"{count}f", blob))


def cosine_similarity(left: bytes, right: bytes) -> float:
    """Compute cosine similarity between two packed embeddings."""

    left_values = _unpack_embedding(left)
    right_values = _unpack_embedding(right)
    if len(left_values) != len(right_values):
        return -1.0
    dot = sum(a * b for a, b in zip(left_values, right_values, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left_values))
    right_norm = math.sqrt(sum(value * value for value in right_values))
    if left_norm == 0 or right_norm == 0:
        return -1.0
    return dot / (left_norm * right_norm)
