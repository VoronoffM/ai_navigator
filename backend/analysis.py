import asyncio
import logging
import os
from collections.abc import Callable
from hashlib import sha256
from typing import Annotated, Literal
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from backend.llm import OPENAI_MODEL, LLMProvider, OpenAIProvider, ProviderError
from backend.replay import Signal
from backend.signal_checks import CHECKS, Check, CheckName, CheckResult, Material

logger = logging.getLogger(__name__)
CHECK_TIMEOUT = 4
COLLECTION_TIMEOUT = 6
LLM_TIMEOUT = 45


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["ollama", "openai"] = "ollama"
    model: str | None = Field(default=None, max_length=150)
    checks: set[CheckName] | None = None


Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=360)]


class Statement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: Text
    materialIds: list[str] = Field(min_length=1, max_length=5)


class Synthesis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    facts: list[Statement] = Field(max_length=3)
    hypotheses: list[Statement] = Field(max_length=3)
    questions: list[Text] = Field(max_length=3)


def resolve_citations(raw: str, materials: dict[str, Material]) -> dict:
    parsed = Synthesis.model_validate_json(raw, strict=True)
    if not (parsed.facts or parsed.hypotheses or parsed.questions):
        raise ValueError("Empty synthesis")
    result = {"questions": parsed.questions}
    for group in ("facts", "hypotheses"):
        result[group] = []
        for statement in getattr(parsed, group):
            ids = list(dict.fromkeys(statement.materialIds))
            if any(item not in materials for item in ids):
                raise ValueError("Unknown material ID")
            cited = [materials[item] for item in ids]
            if any(item.headline_only for item in cited):
                if group != "facts" or len(cited) != 1 or statement.text != cited[0].title:
                    raise ValueError("Unsupported headline-only claim")
            result[group].append({
                "text": statement.text,
                "citations": [{"id": item.id, "source": item.source, "title": item.title, "url": item.url}
                              for item in cited],
            })
    return result


class AnalysisService:
    def __init__(self, provider: LLMProvider, checks: dict[CheckName, Check], *,
                 openai_client: httpx.AsyncClient | None = None):
        self.provider = provider
        self.openai_client = openai_client
        self.checks = checks
        self.models = list(dict.fromkeys(model.strip() for model in os.getenv(
            "ANALYSIS_MODELS", "qwen2.5:3b"
        ).split(",") if model.strip())) or ["qwen2.5:3b"]
        self.default_model = os.getenv("ANALYSIS_DEFAULT_MODEL", self.models[0]).strip()
        if self.default_model not in self.models:
            raise ValueError("ANALYSIS_DEFAULT_MODEL must be included in ANALYSIS_MODELS")
        self.jobs: dict[str, dict] = {}
        self.job_keys: dict[tuple[str, str, str, tuple[CheckName, ...], bytes], str] = {}
        self.tasks: set[asyncio.Task] = set()

    def config(self):
        return {
            "provider": self.provider.name, "models": self.models, "checks": CHECKS,
            "openaiModel": OPENAI_MODEL if self.openai_client is not None else None,
            "defaults": {"model": self.default_model, "checks": list(self.checks)},
        }

    def start(self, event: Signal, profile: Profile, openai_key: str = "") -> dict:
        provider = self.provider
        models, default = self.models, self.default_model
        credential_hash = b""
        if profile.provider == "openai":
            if self.openai_client is None:
                raise ValueError("OpenAI недоступна на этом сервере.")
            provider = OpenAIProvider(self.openai_client, openai_key)
            models, default = [OPENAI_MODEL], OPENAI_MODEL
            credential_hash = sha256(openai_key.encode()).digest()
        model = default if profile.model is None else profile.model
        if model not in models:
            raise ValueError("Выбранная модель отсутствует в настройках сервера.")
        enabled = set(self.checks) if profile.checks is None else profile.checks
        if not enabled.issubset(self.checks):
            raise ValueError("Выбранная проверка недоступна для этого сценария.")
        names = tuple(name for name in self.checks if name in enabled)
        key = (event.event_id, profile.provider, model, names, credential_hash)
        if job_id := self.job_keys.get(key):
            job = self.jobs[job_id]
            if job.get("llm") != "failed":
                return job
        job_id = uuid4().hex
        self.job_keys[key] = job_id
        self.jobs[job_id] = {"id": job_id, "event_id": event.event_id, "status": "collecting"}
        task = asyncio.create_task(self.run(job_id, event, provider, model, names))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return self.jobs[job_id]

    async def shutdown(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def run_check(self, name: CheckName, event: Signal) -> CheckResult:
        try:
            async with asyncio.timeout(CHECK_TIMEOUT):
                return await self.checks[name](event)
        except TimeoutError:
            return CheckResult("unavailable", "Источник не ответил вовремя.")
        except Exception as exc:
            logger.warning("Check %s failed (%s)", name, type(exc).__name__)
            return CheckResult("unavailable", "Не удалось получить данные из источника.")

    async def collect(self, event: Signal, names: tuple[CheckName, ...],
                      on_check: Callable[[CheckName, CheckResult], None] | None = None) -> dict[CheckName, CheckResult]:
        async def check_source(name: CheckName) -> CheckResult:
            result = await self.run_check(name, event)
            if on_check is not None:
                on_check(name, result)
            return result

        tasks = {name: asyncio.create_task(check_source(name)) for name in names}
        try:
            if tasks:
                await asyncio.wait(tasks.values(), timeout=COLLECTION_TIMEOUT)
            return {
                name: (tasks[name].result() if tasks[name].done() else
                       CheckResult("unavailable", "Истекло время сбора контекста."))
                if name in tasks else CheckResult("disabled")
                for name in CHECKS
            }
        finally:
            pending = [task for task in tasks.values() if not task.done()]
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    async def run(self, job_id: str, event: Signal, provider: LLMProvider,
                  model: str, names: tuple[CheckName, ...]):
        running = self.jobs[job_id]
        result = {
            **running, "status": "done", "llm": "skipped", "synthesis": None, "reason": None,
            "checks": {name: CheckResult("unavailable" if name in names else "disabled").payload()
                       for name in CHECKS},
        }

        def record_check(name: CheckName, check: CheckResult) -> None:
            job = self.jobs[job_id]
            self.jobs[job_id] = {
                **job, "completedChecks": {**job.get("completedChecks", {}), name: check.status},
            }

        try:
            checks = await self.collect(event, names, record_check)
            result["checks"] = {name: check.payload() for name, check in checks.items()}
            materials = {item.id: item for check in checks.values() for item in check.materials}
            if materials:
                self.jobs[job_id] = {**running, "status": "analyzing"}
                context = {
                    "event": event.model_dump(mode="json", exclude_none=True),
                    "computedFacts": {name: check.facts for name, check in checks.items() if check.facts},
                    "materials": [item.payload() for item in materials.values()],
                    "coverage": {name: {"status": check.status, "reason": check.reason}
                                 for name, check in checks.items()},
                }
                schema = Synthesis.model_json_schema()
                id_field = schema["$defs"]["Statement"]["properties"]["materialIds"]["items"]
                id_field["enum"] = list(materials)
                async with asyncio.timeout(LLM_TIMEOUT):
                    raw = await provider.generate(model, context, schema)
                result["synthesis"] = resolve_citations(raw, materials)
                result["llm"] = "ready"
        except ProviderError as exc:
            result.update(llm="failed", reason=str(exc))
        except TimeoutError:
            result.update(llm="failed", reason="Модель не ответила вовремя.")
        except ValueError:
            result.update(llm="failed", reason="Ответ модели не прошёл проверку.")
        except Exception as exc:
            logger.warning("Analysis %s failed (%s)", job_id, type(exc).__name__)
            result.update(llm="failed", reason="Не удалось завершить разбор.")
        self.jobs[job_id] = result
