"""Bounded, cancellable analysis lifecycle; original evidence is never mutated."""
import asyncio
import hashlib
import json
import time
from pathlib import Path
from uuid import uuid4

from openai import APIConnectionError, APIStatusError, AuthenticationError, PermissionDeniedError, RateLimitError

from app.assistant.schemas import AnalysisRecord, AnalysisStage
from app.assistant.store import AssistantStore, RESULT_GROWTH_BYTES, AnalysisRevokedError


def normalized_context(context):
    task = context.task
    if task == "brief":
        task = "compare" if len(context.candidates) == 2 else "warning" if context.equipment_id and context.scenario_id else "investigate"
    return context.model_copy(update={"task": task})


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
        self.store = AssistantStore(settings.artifacts_dir / "assistant",
            max_public_records=getattr(settings, "demo_analysis_max_records", 2000),
            max_public_bytes=getattr(settings, "demo_analysis_max_bytes", 32 * 1024 * 1024))
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

    def output_access_reason(self, owner, experiment, consent_required):
        """Saved cloud access is independent of whether another provider call is configured."""
        if self.settings.mode == "replay":
            return "Cloud analysis is unavailable in replay mode."
        if self.settings.mode == "demo" and not self.store.unlocked(owner):
            return "Presenter access has expired."
        if consent_required and not self.store.consent(owner, experiment):
            return "Cloud consent is off for this experiment."
        return None

    def identities(self, loaded, context, live):
        from app.assistant.evidence import build_analysis
        if context.task == "data":
            result = loaded.result
        else:
            result = build_analysis(loaded, normalized_context(context))
        draft = hashlib.sha256(json.dumps({"evidence": result.evidence_digest,
            "context": normalized_context(context).model_dump(mode="json")}, sort_keys=True).encode()).hexdigest()
        # Hash the actual prompt and server tool/output contracts, including task-specific data rules.
        contracts = ["agent.py", "investigation.py", "evidence.py", "schemas.py"]
        if context.task == "data":
            contracts.append("data_review.py")
        version = hashlib.sha256(b"".join((Path(__file__).parent / name).read_bytes() for name in contracts)).hexdigest()
        from app.assistant import agent, investigation
        identity = {"draft": draft, "contracts": version, "mode": self.settings.mode,
                    "prompt": investigation.PROMPT_VERSION, "instruction": agent.INSTRUCTION,
                    "provider": "openai" if live else "evidence", "model": self.settings.assistant_model if live else None}
        return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest(), draft, result.evidence_digest

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
        if self.settings.mode in {"demo", "replay"}:
            self.store.expire_public()
        tools = loaded if context.task == "data" else EvidenceTools(loaded, context)
        reason = self.live_reason(owner, context.consent_scope, consent_required)
        fingerprint, draft_fingerprint, evidence_digest = self.identities(loaded, context, not reason)
        if reuse:
            saved = self.store.latest(owner, fingerprint) or self.store.latest_scoped(owner, draft_fingerprint)
            if saved:
                denied = self.output_access_reason(owner, context.consent_scope, consent_required)
                origins = self.store.provenance(saved.id, owner)
                if not denied or origins[0] == "evidence":
                    if saved.result is None:
                        saved.result = tools.local()
                    if denied and origins[1] != "evidence":
                        saved.brief_text = None
                        saved.brief_saved_at = None
                    return self.restore(saved, context, tools.result.title)
        liveTools = tools.fresh()
        result = tools.local()
        now = time.time()
        record = AnalysisRecord(id=str(uuid4()), context=context, status="completed", created_at=now, updated_at=now,
            stages=[AnalysisStage(id="evidence", label="Collect evidence", status="completed"),
                    AnalysisStage(id="explain", label="Investigate evidence", status="completed"),
                    AnalysisStage(id="verify", label="Verify references", status="completed")], result=result,
            cache_fingerprint=fingerprint, draft_fingerprint=draft_fingerprint)
        draft = self.store.latest_draft(owner, draft_fingerprint, evidence_digest, context)
        draft_origin = self.store.provenance(draft.id, owner)[1] if draft else None
        if draft and (draft_origin == "evidence" or not self.output_access_reason(owner, context.consent_scope, consent_required)):
            from app.assistant.evidence import with_brief
            generated = (draft.result.brief_draft or with_brief(draft.result, draft.context.model_copy(update={"task": "brief"})).brief_draft) if draft.result else None
            # Unedited generated text should improve with the new analysis too.
            if draft.brief_text != generated:
                record.brief_text = draft.brief_text
                record.brief_saved_at = draft.brief_saved_at
        if not reason and self.tasks:
            reason = "Another live analysis is running. Recorded evidence is ready."
        if reason:
            record.result.fallback_reason = reason
            record.cache_fingerprint = self.identities(loaded, context, False)[0]
            self.store.save(record, owner, public=self.settings.mode in {"demo", "replay"}, brief_origin=draft_origin if record.brief_text is not None else None)
            return record
        record.status = "running"
        record.stages[1].status = "running"
        record.stages[2].status = "pending"
        self.store.save(record, owner, public=self.settings.mode in {"demo", "replay"}, brief_origin=draft_origin if record.brief_text is not None else None)
        self.contexts[record.id] = (owner, context.consent_scope, consent_required)
        evidence_fingerprint = self.identities(loaded, context, False)[0]
        self.tasks[record.id] = asyncio.create_task(self._run(record, owner, consent_required, liveTools, evidence_fingerprint))
        return record

    async def _run(self, record, owner, consent_required, tools, evidence_fingerprint):
        from app.assistant.provider import enhance_analysis
        try:
            reason = self.live_reason(owner, record.context.consent_scope, consent_required)
            if reason:
                record.result.fallback_reason = reason
            else:
                result = await asyncio.wait_for(enhance_analysis(record.result, record.context, self.settings, tools=tools),
                    timeout=self.settings.assistant_timeout_seconds)
                if self.settings.mode in {"demo", "replay"} and len(result.model_dump_json().encode()) > len(record.result.model_dump_json().encode()) + RESULT_GROWTH_BYTES - 1024:
                    raise ValueError("Generated analysis exceeds its bounded result capacity.")
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
            if record.result and record.result.mode == "evidence":
                record.cache_fingerprint = evidence_fingerprint
            try:
                if not self.store.revoked(record.id, owner):
                    self.store.save(record, owner, public=self.settings.mode in {"demo", "replay"})
            except AnalysisRevokedError:
                # Revocation won the transactional write race; its cancelled record is authoritative.
                pass
            finally:
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
                self.store.save(record, owner, public=self.settings.mode in {"demo", "replay"})
            self.tasks.pop(id, None)
            self.contexts.pop(id, None)
        return record

    async def revoke(self, owner, experiment):
        # Clear saved output and revoke consent atomically before any cancellation await.
        self.store.revoke_results(owner, experiment)
        for id, context in list(self.contexts.items()):
            if context[:2] == (owner, experiment):
                await self.cancel(id, owner)

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)



