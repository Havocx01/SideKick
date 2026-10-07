"""Contextual analysis endpoints with session isolation and explicit cloud consent."""
import hashlib
import re
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.deps import bundle
from app.assistant.exports import export_brief
from app.assistant.store import PublicLimitError
from app.assistant.schemas import AnalysisRequest, AnalysisRecord, AssistantAccess, AssistantCapabilities, BriefUpdate, ConsentState, ConsentUpdate
from app.experiments.demo import owner as demo_owner, public_origin

router = APIRouter(prefix="/api/assistant", tags=["assistant"])
COOKIE = "sidekick_assistant"
DISCLOSURE = ("Sent to OpenAI: the task type, pseudonymous model and fault-case aliases, evaluation partition, finding categories, "
              "and recorded metric values with their units, such as detection rates, early alarm time, passed-case counts and summarized "
              "warning events. Not sent: CSV files, raw sensor readings, equipment IDs, model names, filenames and pilot contact details. "
              "Requests use store=false, but OpenAI may retain API abuse-monitoring logs for up to 30 days, and exceptions may apply.")


def service(request: Request):
    result = request.app.state.assistant
    if not result.settings.assistant_enabled:
        raise HTTPException(404, "Analysis is unavailable.")
    return result


def guard(request: Request):
    if request.headers.get("x-sidekick-request") != "1":
        raise HTTPException(403, "Use the Sidekick interface for this action.")
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != public_origin(request):
        raise HTTPException(403, "This action must come from the Sidekick origin.")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Cross-site actions are unavailable.")


def visitor(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    if service(request).settings.mode == "demo":
        return demo_owner(request)
    token = request.cookies.get(COOKIE, "")
    if not re.fullmatch(r"[a-f0-9]{64}", token):
        token = secrets.token_hex(32)
        response.set_cookie(COOKIE, token, httponly=True, secure=public_origin(request).startswith("https:"), samesite="strict", max_age=86400)
    return hashlib.sha256(token.encode()).hexdigest()


def upload_context(request, experiment_id):
    if not experiment_id:
        return False
    workspace = request.app.state.jobs.workspace
    experiment = workspace.get("experiments", experiment_id)
    dataset = workspace.get("datasets", experiment["dataset_id"])
    return dataset.get("source") == "upload"


def owned_record(id, request, response):
    assistant = service(request)
    who = visitor(request, response)
    try:
        record = assistant.store.get(id, who)
    except KeyError:
        raise HTTPException(404, "Analysis not found.") from None
    if assistant.settings.mode == "demo" and record.created_at < time.time() - 86400:
        raise HTTPException(404, "Analysis expired. Start a new analysis.")
    loaded = bundle(request, record.context.experiment_id)
    consent_required = upload_context(request, record.context.experiment_id)
    revoked = record.result is not None and record.result.mode == "ai" and assistant.live_reason(who, record.context.experiment_id, consent_required)
    if record.result is None or revoked:
        from app.assistant.evidence import build_analysis
        record.result = build_analysis(loaded, record.context)
        if revoked:
            record.result.fallback_reason = "Showing recorded evidence; live analysis access is off."
            record.brief_text = None
            record.brief_saved_at = None
    return record, who


@router.get("/capabilities", response_model=AssistantCapabilities)
def capabilities(request: Request, response: Response, experiment_id: str | None = None):
    assistant = service(request)
    bundle(request, experiment_id)
    who = visitor(request, response)
    required = upload_context(request, experiment_id)
    reason = assistant.live_reason(who, experiment_id, required)
    return AssistantCapabilities(tasks=list(assistant.settings.assistant_tasks), live_available=reason is None,
        unlock_available=assistant.settings.mode == "demo" and bool(assistant.settings.assistant_presenter_code),
        unlocked=assistant.settings.mode == "full" or assistant.store.unlocked(who), consent_required=required,
        consent_granted=not required or assistant.store.consent(who, experiment_id), mode=assistant.settings.mode,
        note=reason or "Live analysis is available.")


@router.post("/analyses", response_model=AnalysisRecord, dependencies=[Depends(guard)])
async def create(payload: AnalysisRequest, request: Request, response: Response):
    if payload.task not in service(request).settings.assistant_tasks:
        raise HTTPException(403, "This analysis is not enabled.")
    loaded = bundle(request, payload.experiment_id)
    try:
        return await service(request).create(loaded, payload, visitor(request, response), upload_context(request, payload.experiment_id))
    except PublicLimitError as error:
        raise HTTPException(429, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.get("/analyses/{id}", response_model=AnalysisRecord)
def get_analysis(id: str, request: Request, response: Response):
    return owned_record(id, request, response)[0]


@router.post("/analyses/{id}/cancel", response_model=AnalysisRecord, dependencies=[Depends(guard)])
async def cancel(id: str, request: Request, response: Response):
    _, who = owned_record(id, request, response)
    await service(request).cancel(id, who)
    return owned_record(id, request, response)[0]


@router.get("/consent/{experiment_id}", response_model=ConsentState)
def consent(experiment_id: str, request: Request, response: Response):
    bundle(request, experiment_id)
    who = visitor(request, response)
    return ConsentState(experiment_id=experiment_id, allowed=service(request).store.consent(who, experiment_id), disclosure=DISCLOSURE)


@router.post("/consent/{experiment_id}", response_model=ConsentState, dependencies=[Depends(guard)])
async def set_consent(experiment_id: str, payload: ConsentUpdate, request: Request, response: Response):
    bundle(request, experiment_id)
    who = visitor(request, response)
    assistant = service(request)
    if payload.allowed:
        assistant.store.set_consent(who, experiment_id, True)
    else:
        await assistant.revoke(who, experiment_id)
    return ConsentState(experiment_id=experiment_id, allowed=payload.allowed, disclosure=DISCLOSURE)


@router.post("/access", dependencies=[Depends(guard)])
def unlock(payload: AssistantAccess, request: Request, response: Response):
    assistant = service(request)
    who = visitor(request, response)
    if assistant.settings.mode != "demo" or not assistant.settings.assistant_presenter_code:
        raise HTTPException(403, "Presenter access is unavailable.")
    address = hashlib.sha256((request.client.host if request.client else "unknown").encode()).hexdigest()
    try:
        assistant.store.attempt(address)
    except ValueError as error:
        raise HTTPException(429, str(error)) from error
    if not secrets.compare_digest(payload.code.encode(), assistant.settings.assistant_presenter_code.encode()):
        raise HTTPException(403, "Incorrect access code.")
    assistant.store.unlock(who)
    return {"unlocked": True}


@router.post("/analyses/{id}/brief", response_model=AnalysisRecord, dependencies=[Depends(guard)])
def save_brief(id: str, payload: BriefUpdate, request: Request, response: Response):
    record, who = owned_record(id, request, response)
    if record.status != "completed":
        raise HTTPException(409, "Wait for the analysis to finish before saving a brief.")
    record.brief_text = payload.text
    record.brief_saved_at = time.time()
    record.updated_at = time.time()
    service(request).store.save(record, who)
    return record


@router.get("/analyses/{id}/export")
def export(id: str, request: Request, response: Response):
    record, _ = owned_record(id, request, response)
    if record.status != "completed":
        raise HTTPException(409, "Wait for the analysis to finish before exporting.")
    return Response(export_brief(record), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="sidekick-review-{record.id}.zip"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})



