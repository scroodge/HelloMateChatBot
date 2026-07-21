"""Owner-triggered, credential-safe Eval Lab candidate runs."""
from __future__ import annotations

import json
from pathlib import Path

from app.config import Config
from app.evals.core import load_cases, run_cases, summarize
from app.services.llm.ollama_provider import OllamaProvider
from app.services.llm.openai_provider import OpenAIProvider

_KEY = "eval_candidates_v1"


class CandidateEvaluationService:
    def __init__(self, settings: object, config: Config) -> None:
        self.settings, self.config = settings, config

    def list(self) -> list[dict[str, object]]:
        try:
            return json.loads(self.settings.get_bot_setting(_KEY, "[]"))
        except json.JSONDecodeError:
            return []

    def defaults(self) -> dict[str, str]:
        return {
            "provider": self.config.llm_provider,
            "model": self.config.llm_model,
            "base_url": self.config.llm_base_url,
        }

    def add(self, name: str, provider: str, model: str, base_url: str) -> dict[str, object]:
        if provider not in {"ollama", "openai"} or not name.strip() or not model.strip():
            raise ValueError("Name, provider and model are required")
        items = self.list()
        if any(
            item["provider"] == provider
            and item["model"] == model.strip()
            and item["base_url"] == base_url.strip()
            for item in items
        ):
            raise ValueError("This provider, model and base URL candidate already exists")
        item = {"id": f"candidate-{len(items) + 1}", "name": name.strip()[:80], "provider": provider, "model": model.strip()[:160], "base_url": base_url.strip(), "status": "new"}
        items.append(item)
        self.settings.set_bot_setting(_KEY, json.dumps(items, ensure_ascii=False))
        return item

    async def evaluate(self, candidate_id: str) -> dict[str, object] | None:
        items = self.list()
        candidate = next((item for item in items if item["id"] == candidate_id), None)
        if candidate is None:
            return None
        cases = load_cases(Path("evals/datasets/regression.jsonl"))
        provider = self._provider(candidate)
        results = await run_cases(cases, provider, prompt_version=str(candidate["id"]))
        summary = summarize(results)
        candidate["summary"] = summary
        candidate["status"] = "passed" if not summary["hard_failure_count"] and summary["pass_rate"] == 1 else "failed"
        self.settings.set_bot_setting(_KEY, json.dumps(items, ensure_ascii=False))
        return candidate

    def _provider(self, candidate: dict[str, object]) -> object:
        base_url = str(candidate["base_url"]) or self.config.llm_base_url
        if candidate["provider"] == "openai":
            return OpenAIProvider(base_url, str(candidate["model"]), self.config.llm_api_key, max_tokens=512, temperature=0.0)
        return OllamaProvider(base_url, str(candidate["model"]), max_tokens=512, temperature=0.0)
