"""Ollama HTTP provider."""

from __future__ import annotations

import httpx


class OllamaProvider:
    """Call a local or remote Ollama server."""

    def __init__(self, base_url: str, model: str, max_tokens: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens

    async def complete(self, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": self.max_tokens},
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        message = data.get("message", {})
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Ollama returned an empty response.")
        return content.strip()

    async def transcribe(self, audio_bytes: bytes, model: str = "whisper") -> str:
        files = {"file": ("voice.ogg", audio_bytes, "audio/ogg")}
        data = {"model": model}
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(f"{self.base_url}/api/transcribe", data=data, files=files)
            response.raise_for_status()
            payload = response.json()
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Ollama transcription returned empty text.")
        return text.strip()
