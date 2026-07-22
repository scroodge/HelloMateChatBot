"""Ollama HTTP provider."""

from __future__ import annotations

from app.models.generation import GenerationRequest, GenerationResult
from app.services.llm.http_client import ResilientHttpClient


class OllamaProvider:
    """Call a local or remote Ollama server."""

    # Stop the model from continuing into a fabricated next turn. The few-shot
    # block and labelled context can otherwise tempt a weak model to keep going
    # ("Контакт: …" / "Ответ: …") or emit meta-instructions to itself.
    _STOP = ["\nКонтакт:", "\nContact:", "\nОтвет:", "\nReply:"]
    provider_name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        max_tokens: int,
        temperature: float = 0.7,
        timeout_seconds: float = 60.0,
        max_concurrency: int = 4,
        max_retries: int = 1,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._http = ResilientHttpClient(
            timeout_seconds=timeout_seconds,
            max_concurrency=max_concurrency,
            max_retries=max_retries,
        )

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        from time import monotonic

        started = monotonic()
        payload = {
            "model": self.model,
            "messages": request.messages,
            "stream": False,
            "options": {
                "num_predict": self.max_tokens,
                "temperature": self.temperature,
                "stop": self._STOP,
            },
        }
        response = await self._http.post(f"{self.base_url}/api/chat", json=payload)
        data = response.json()
        message = data.get("message", {})
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Ollama returned an empty response.")
        return GenerationResult(
            text=content.strip(),
            provider=self.provider_name,
            model=self.model,
            response_id=None,
            input_tokens=data.get("prompt_eval_count"),
            output_tokens=data.get("eval_count"),
            cached_tokens=None,
            finish_reason=data.get("done_reason"),
            latency_ms=round((monotonic() - started) * 1000),
        )

    async def complete(self, messages: list[dict[str, str]]) -> str:
        return (await self.generate(GenerationRequest(messages, "reply", None, "v1", "v1"))).text

    async def transcribe(self, audio_bytes: bytes, model: str = "whisper") -> str:
        files = {"file": ("voice.ogg", audio_bytes, "audio/ogg")}
        data = {"model": model}
        response = await self._http.post(
            f"{self.base_url}/api/transcribe", data=data, files=files
        )
        payload = response.json()
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Ollama transcription returned empty text.")
        return text.strip()

    async def aclose(self) -> None:
        await self._http.aclose()

    def health(self) -> dict[str, object]:
        return self._http.health()
