"""OpenAI-compatible HTTP provider."""

from __future__ import annotations

import httpx

from app.models.generation import GenerationRequest, GenerationResult


class OpenAIProvider:
    """Call an OpenAI-compatible chat completions API."""

    _STOP = ["\nКонтакт:", "\nContact:", "\nОтвет:", "\nReply:"]
    provider_name = "openai"

    @property
    def _uses_completion_tokens(self) -> bool:
        """GPT-5 rejects the legacy ``max_tokens`` Chat Completions field.

        OpenRouter and other compatible endpoints retain their existing payload
        shape, so this is intentionally limited to OpenAI's first-party API.
        """

        return self.base_url == "https://api.openai.com" and self.model.startswith("gpt-5")

    def __init__(
        self, base_url: str, model: str, api_key: str, max_tokens: int, temperature: float = 0.7
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.temperature = temperature

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        from time import monotonic

        started = monotonic()
        if not self.api_key:
            raise RuntimeError("LLM_API_KEY is required for the OpenAI provider.")

        payload = {
            "model": self.model,
            "messages": request.messages,
            "temperature": self.temperature,
            "stop": self._STOP,
        }
        payload["max_completion_tokens" if self._uses_completion_tokens else "max_tokens"] = (
            self.max_tokens
        )
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
        usage = data.get("usage") or {}
        choice = choices[0]
        details = usage.get("prompt_tokens_details") or {}
        return GenerationResult(
            text=content.strip(),
            provider=self.provider_name,
            model=data.get("model", self.model),
            response_id=data.get("id"),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            cached_tokens=details.get("cached_tokens"),
            finish_reason=choice.get("finish_reason"),
            latency_ms=round((monotonic() - started) * 1000),
        )

    async def complete(self, messages: list[dict[str, str]]) -> str:
        return (await self.generate(GenerationRequest(messages, "reply", None, "v1", "v1"))).text

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
