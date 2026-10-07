"""Bounded, cancellable analysis lifecycle; original evidence is never mutated."""
import asyncio
import time
from uuid import uuid4

from app.assistant.schemas import AnalysisRecord, AnalysisStage
from app.assistant.store import AssistantStore


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

    async def create(self, loaded, context, owner, consent_required):
        from app.assistant.evidence import build_analysis
        if self.settings.mode == "demo":
            self.store.admit_evidence(owner)
        result = build_analysis(loaded, context)
        now = time.time()
        record = AnalysisRecord(id=str(uuid4()), context=context, status="completed", created_at=now, updated_at=now,
            stages=[AnalysisStage(id="evidence", label="Collect evidence", status="completed"),
                    AnalysisStage(id="explain", label="Explain findings", status="completed"),
                    AnalysisStage(id="verify", label="Verify references", status="completed")], result=result)
        reason = self.live_reason(owner, context.experiment_id, consent_required)
        if not reason and self.tasks:
            reason = "Another live analysis is running. Recorded evidence is ready."
        if not reason and self.settings.mode == "demo":
            try:
                self.store.admit(owner, self.settings.assistant_session_limit, self.settings.assistant_daily_limit)
            except ValueError as error:
                reason = str(error)
        if reason:
            record.result.fallback_reason = reason
            self.store.save(record, owner, public=self.settings.mode == "demo")
            return record
        record.status = "running"
        record.stages[1].status = "running"
        record.stages[2].status = "pending"
        self.store.save(record, owner, public=self.settings.mode == "demo")
        self.contexts[record.id] = (owner, context.experiment_id, consent_required)
        self.tasks[record.id] = asyncio.create_task(self._run(record, owner, consent_required))
        return record

    async def _run(self, record, owner, consent_required):
        from app.assistant.provider import enhance_analysis
        try:
            reason = self.live_reason(owner, record.context.experiment_id, consent_required)
            if reason:
                record.result.fallback_reason = reason
            else:
                result = await asyncio.wait_for(enhance_analysis(record.result, record.context, self.settings),
                    timeout=self.settings.assistant_timeout_seconds)
                reason = self.live_reason(owner, record.context.experiment_id, consent_required)
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
        except Exception:
            record.status = "completed"
            record.result.fallback_reason = "Live analysis is unavailable. Showing recorded evidence."
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



