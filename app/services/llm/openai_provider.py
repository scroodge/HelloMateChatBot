"""OpenAI-compatible HTTP provider."""

from __future__ import annotations

import httpx


class OpenAIProvider:
    """Call an OpenAI-compatible chat completions API."""

    def __init__(self, base_url: str, model: str, api_key: str, max_tokens: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens

    async def complete(self, messages: list[dict[str, str]]) -> str:
        if not self.api_key:
            raise RuntimeError("LLM_API_KEY is required for the OpenAI provider.")

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError("OpenAI-compatible API returned no choices.")
        message = choices[0].get("message", {})
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("OpenAI-compatible API returned an empty response.")
        return content.strip()

    async def transcribe(self, audio_bytes: bytes, model: str = "whisper-1") -> str:
        if not self.api_key:
            raise RuntimeError("LLM_API_KEY is required for OpenAI transcription.")

        files = {"file": ("voice.ogg", audio_bytes, "audio/ogg")}
        data = {"model": model}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/v1/audio/transcriptions",
                data=data,
                files=files,
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("OpenAI transcription returned empty text.")
        return text.strip()
