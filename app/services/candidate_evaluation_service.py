"""Owner-triggered, credential-safe Eval Lab candidate runs."""
from __future__ import annotations

import json
import os
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

    def add(
        self, name: str, provider: str, model: str, base_url: str, credential_id: str = "default"
    ) -> dict[str, object]:
        if provider not in {"ollama", "openai"} or not name.strip() or not model.strip():
            raise ValueError("Name, provider and model are required")
        items = self.list()
        if any(
            item["provider"] == provider
            and item["model"] == model.strip()
            and item["base_url"] == base_url.strip()
            and item.get("credential_id", "default") == credential_id
            for item in items
        ):
            raise ValueError("This provider, model and base URL candidate already exists")
        if credential_id not in self.credential_ids():
            raise ValueError("Unknown server-side credential ID")
        item = {"id": f"candidate-{len(items) + 1}", "name": name.strip()[:80], "provider": provider, "model": model.strip()[:160], "base_url": base_url.strip(), "credential_id": credential_id, "status": "new"}
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
            return OpenAIProvider(base_url, str(candidate["model"]), self._credential(candidate), max_tokens=512, temperature=0.0)
        return OllamaProvider(base_url, str(candidate["model"]), max_tokens=512, temperature=0.0)

    def credential_ids(self) -> list[str]:
        return ["default", *self._credentials().keys()]

    def _credential(self, candidate: dict[str, object]) -> str:
        credential_id = str(candidate.get("credential_id", "default"))
        if credential_id == "default":
            return self.config.llm_api_key
        return self._credentials()[credential_id]

    @staticmethod
    def _credentials() -> dict[str, str]:
        try:
            values = json.loads(os.getenv("EVAL_PROVIDER_KEYS_JSON", "{}"))
        except json.JSONDecodeError:
            return {}
        return {str(key): str(value) for key, value in values.items() if value}
