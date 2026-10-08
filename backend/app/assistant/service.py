"""Bounded, cancellable analysis lifecycle; original evidence is never mutated."""
import asyncio
import time
from uuid import uuid4

from openai import APIConnectionError, APIStatusError, AuthenticationError, PermissionDeniedError, RateLimitError

from app.assistant.schemas import AnalysisRecord, AnalysisStage
from app.assistant.store import AssistantStore


def provider_failure(error):
    """Explain known provider failures without exposing its response or credentials."""
    if isinstance(error, AuthenticationError):
        return "OpenAI rejected the API key. Replace OPENAI_API_KEY and restart the server."
    if isinstance(error, PermissionDeniedError):
        return "The API key lacks access. Check the OpenAI project and model permissions."
    if isinstance(error, RateLimitError):
        if error.code in {"insufficient_quota", "billing_hard_limit_reached", "organization_spend_limit_exceeded"}:
            return "OpenAI API credit or spending limit reached. Check API billing and limits."
        return "OpenAI rate limit reached. Wait a moment, then try again."
    if isinstance(error, APIConnectionError):
        return "Cannot reach OpenAI. Check the server's internet connection, then try again."
    if isinstance(error, APIStatusError) and error.status_code == 404:
        return "The configured AI model is unavailable. Check SIDEKICK_ASSISTANT_MODEL and model access."
    return "Live analysis is unavailable. Try again later."


class AssistantService:
    def __init__(self, settings):
        self.settings = settings
        self.store = AssistantStore(settings.artifacts_dir / "assistant")
        self.tasks = {}
        self.contexts = {}

    def live_reason(self, owner, experiment, consent_required):
        settings = self.settings
        if settings.mode == "replay" or not settings.assistant_live_enabled or not settings.openai_api_key:
            return "Recorded evidence analysis. Live AI is not configured."
        if settings.mode == "demo" and not self.store.unlocked(owner):
            return "Recorded evidence analysis. Presenter access enables live AI."
        if consent_required and not self.store.consent(owner, experiment):
            return "Cloud analysis is off for this experiment."
        return None

    @staticmethod
    def fingerprint(loaded, context):
        from app.assistant.evidence import build_analysis
        if context.task == "data":
            result = loaded.result
        else:
            task = context.task
            if task == "brief":
                task = "compare" if len(context.candidates) == 2 else "warning" if context.equipment_id and context.scenario_id else "investigate"
            result = build_analysis(loaded, context.model_copy(update={"task": task}))
        return f"{result.prompt_version}:{result.evidence_digest}"

    @staticmethod
    def restore(record, context, title):
        from app.assistant.evidence import with_brief
        restored = record.model_copy(deep=True)
        restored.context = context
        restored.reused = True
        restored.result = with_brief(restored.result, context)
        restored.result.title = title
        return restored

    async def create(self, loaded, context, owner, consent_required, reuse=False):
        from app.assistant.investigation import EvidenceTools
        if self.settings.mode == "demo":
            self.store.expire_public()
        tools = loaded if context.task == "data" else EvidenceTools(loaded, context)
        fingerprint = self.fingerprint(loaded, context)
        reason = self.live_reason(owner, context.consent_scope, consent_required)
        if reuse:
            saved = self.store.latest(owner, fingerprint)
            if saved and (saved.result.mode != "ai" or not reason):
                return self.restore(saved, context, tools.result.title)
        liveTools = tools.fresh()
        result = tools.local()
        now = time.time()
        record = AnalysisRecord(id=str(uuid4()), context=context, status="completed", created_at=now, updated_at=now,
            stages=[AnalysisStage(id="evidence", label="Collect evidence", status="completed"),
                    AnalysisStage(id="explain", label="Investigate evidence", status="completed"),
                    AnalysisStage(id="verify", label="Verify references", status="completed")], result=result,
            cache_fingerprint=fingerprint)
        if not reason and self.tasks:
            reason = "Another live analysis is running. Recorded evidence is ready."
        if reason:
            record.result.fallback_reason = reason
            self.store.save(record, owner, public=self.settings.mode == "demo")
            return record
        record.status = "running"
        record.stages[1].status = "running"
        record.stages[2].status = "pending"
        self.store.save(record, owner, public=self.settings.mode == "demo")
        self.contexts[record.id] = (owner, context.consent_scope, consent_required)
        self.tasks[record.id] = asyncio.create_task(self._run(record, owner, consent_required, liveTools))
        return record

    async def _run(self, record, owner, consent_required, tools):
        from app.assistant.provider import enhance_analysis
        try:
            reason = self.live_reason(owner, record.context.consent_scope, consent_required)
            if reason:
                record.result.fallback_reason = reason
            else:
                result = await asyncio.wait_for(enhance_analysis(record.result, record.context, self.settings, tools=tools),
                    timeout=self.settings.assistant_timeout_seconds)
                reason = self.live_reason(owner, record.context.consent_scope, consent_required)
                if reason:
                    record.result.fallback_reason = reason
                else:
                    record.result = result
            record.status = "completed"
        except asyncio.CancelledError:
            record.status = "cancelled"
            record.error = "Analysis cancelled. Recorded evidence remains available."
        except TimeoutError:
            record.status = "completed"
            record.result.fallback_reason = "Live analysis timed out. Showing recorded evidence."
        except ValueError:
            record.status = "completed"
            record.result.fallback_reason = "Live analysis failed verification. Showing recorded evidence."
        except Exception as error:
            record.status = "completed"
            record.result.fallback_reason = provider_failure(error) + " Showing recorded evidence."
        finally:
            for stage in record.stages:
                stage.status = "completed" if record.status == "completed" else "failed"
            record.updated_at = time.time()
            self.store.save(record, owner, public=self.settings.mode == "demo")
            self.tasks.pop(record.id, None)
            self.contexts.pop(record.id, None)

    async def cancel(self, id, owner):
        record = self.store.get(id, owner)
        task = self.tasks.get(id)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            record = self.store.get(id, owner)
            # A task cancelled before its first instruction cannot persist its finally block.
            if record.status == "running":
                record.status = "cancelled"
                record.updated_at = time.time()
                self.store.save(record, owner, public=self.settings.mode == "demo")
            self.tasks.pop(id, None)
            self.contexts.pop(id, None)
        return record

    async def revoke(self, owner, experiment):
        self.store.set_consent(owner, experiment, False)
        for id, context in list(self.contexts.items()):
            if context[:2] == (owner, experiment):
                await self.cancel(id, owner)
        self.store.revoke_results(owner, experiment)

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)



