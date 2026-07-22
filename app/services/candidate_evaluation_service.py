"""Owner-triggered, credential-safe Eval Lab candidate runs."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from app.config import Config
from app.evals.core import load_cases, run_cases, summarize
from app.models.generation import GenerationRequest, GenerationResult
from app.services.llm.ollama_provider import OllamaProvider
from app.services.llm.openai_provider import OpenAIProvider

_KEY = "eval_candidates_v1"

if TYPE_CHECKING:
    from app.database.repositories.background_jobs import BackgroundJobsRepository


class CandidateEvaluationService:
    def __init__(
        self,
        settings: object,
        config: Config,
        background_jobs: BackgroundJobsRepository | None = None,
    ) -> None:
        self.settings, self.config = settings, config
        self._background_jobs = background_jobs

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

    def matrix(self) -> list[dict[str, object]]:
        """Return comparable, owner-safe metrics for completed candidates."""

        rows: list[dict[str, object]] = []
        for candidate in self.list():
            summary = candidate.get("summary")
            rows.append(
                {
                    "id": candidate["id"],
                    "name": candidate["name"],
                    "provider": candidate["provider"],
                    "model": candidate["model"],
                    "status": candidate["status"],
                    "pass_rate": summary.get("pass_rate") if summary else None,
                    "hard_failure_count": summary.get("hard_failure_count") if summary else None,
                    "mean_latency_ms": summary.get("mean_latency_ms") if summary else None,
                    "p95_latency_ms": summary.get("p95_latency_ms") if summary else None,
                    "input_tokens": summary.get("input_tokens") if summary else None,
                    "output_tokens": summary.get("output_tokens") if summary else None,
                }
            )
        return rows

    async def generate_shadow(
        self, candidate_id: str, messages: list[dict[str, str]]
    ) -> GenerationResult:
        candidate = next((item for item in self.list() if item["id"] == candidate_id), None)
        if candidate is None:
            raise ValueError("Candidate not found")
        provider = self._provider(candidate)
        try:
            return await provider.generate(
                GenerationRequest(messages, "shadow", None, "baseline", "baseline")
            )
        finally:
            close_provider = getattr(provider, "aclose", None)
            if close_provider is not None:
                await close_provider()

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
        item = {
            "id": f"candidate-{uuid4().hex[:12]}",
            "name": name.strip()[:80],
            "provider": provider,
            "model": model.strip()[:160],
            "base_url": base_url.strip(),
            "credential_id": credential_id,
            "status": "new",
        }
        items.append(item)
        self.settings.set_bot_setting(_KEY, json.dumps(items, ensure_ascii=False))
        return item

    def delete(self, candidate_id: str) -> bool:
        items = self.list()
        remaining = [item for item in items if item["id"] != candidate_id]
        if len(remaining) == len(items):
            return False
        self.settings.set_bot_setting(_KEY, json.dumps(remaining, ensure_ascii=False))
        return True

    def enqueue_evaluation(self, candidate_id: str) -> dict[str, object] | None:
        if self._background_jobs is None:
            raise RuntimeError("Background worker is not enabled")
        items = self.list()
        candidate = next((item for item in items if item["id"] == candidate_id), None)
        if candidate is None:
            return None
        if candidate.get("status") in {"queued", "running"}:
            return candidate

        version = int(candidate.get("evaluation_version", 0)) + 1
        job = self._background_jobs.enqueue(
            "candidate_evaluation",
            {"candidate_id": candidate_id},
            idempotency_key=f"candidate-evaluation:{candidate_id}:{version}",
            max_attempts=3,
        )
        candidate["evaluation_version"] = version
        candidate["job_id"] = job.id
        candidate["status"] = "queued"
        candidate.pop("summary", None)
        self._save(items)
        return candidate

    async def evaluate(self, candidate_id: str) -> dict[str, object] | None:
        items = self.list()
        candidate = next((item for item in items if item["id"] == candidate_id), None)
        if candidate is None:
            return None
        candidate["status"] = "running"
        self._save(items)
        provider: object | None = None
        try:
            cases = load_cases(Path("evals/datasets/regression.jsonl"))
            provider = self._provider(candidate)
            results = await run_cases(cases, provider, prompt_version=str(candidate["id"]))
            summary = summarize(results)
        except Exception as exc:
            summary = {
                "case_count": 0,
                "passed_count": 0,
                "pass_rate": 0.0,
                "hard_failure_count": 1,
                "error": str(exc)[:500],
            }
        finally:
            close_provider = getattr(provider, "aclose", None)
            if close_provider is not None:
                try:
                    await close_provider()
                except Exception:
                    pass
        candidate["summary"] = summary
        candidate["status"] = (
            "passed"
            if not summary["hard_failure_count"] and summary["pass_rate"] == 1
            else "failed"
        )
        self._save(items)
        return candidate

    def _save(self, items: list[dict[str, object]]) -> None:
        self.settings.set_bot_setting(_KEY, json.dumps(items, ensure_ascii=False))

    def _provider(self, candidate: dict[str, object]) -> object:
        base_url = str(candidate["base_url"]) or self.config.llm_base_url
        if candidate["provider"] == "openai":
            is_direct_openai_gpt5 = (
                base_url.rstrip("/") == "https://api.openai.com"
                and str(candidate["model"]).startswith("gpt-5")
            )
            return OpenAIProvider(
                base_url,
                str(candidate["model"]),
                self._credential(candidate),
                max_tokens=1024 if is_direct_openai_gpt5 else 512,
                temperature=0.0,
                reasoning_effort="minimal" if is_direct_openai_gpt5 else None,
            )
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
