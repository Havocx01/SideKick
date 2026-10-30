"""Saved fault investigations: create, start, inspect, reduce, compare remedies."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from app.api.routes_experiments import library_owner
from app.config import get_settings
from app.experiments.demo import public_origin
from app.investigator.schemas import (ContextInfo, InvestigationCreate, InvestigationSummary, InvestigationView, ReduceRequest, RemedyRequest,
    ReplayCheck, StartRequest)
from app.investigator.service import Conflict, InvestigationService

router = APIRouter(prefix="/api/investigations", tags=["investigations"])


def service(request: Request) -> InvestigationService:
    if get_settings().mode != "full":
        raise HTTPException(403, "Fault investigations run locally. Start Sidekick in full mode to use them.")
    origin = request.headers.get("origin")
    if request.method == "POST" and origin and origin not in (*get_settings().cors_origins, public_origin(request)):
        raise HTTPException(403, "Investigation changes must come from the Sidekick interface.")
    found = getattr(request.app.state, "investigations", None)
    if found is None:
        raise HTTPException(503, "The investigation workspace is not ready.")
    return found


def call(action, *args, **kwargs):
    try:
        return action(*args, **kwargs)
    except KeyError:
        raise HTTPException(404, "This investigation or record is unavailable.") from None
    except PermissionError as error:
        raise HTTPException(403, str(error)) from None
    except Conflict as error:
        raise HTTPException(409, str(error)) from None
    except (ValueError, ValidationError) as error:
        raise HTTPException(422, str(error).splitlines()[0][:300]) from None


def consent(request: Request):
    assistant = request.app.state.assistant
    return lambda: bool(assistant.workspace_consent())


@router.get("/contexts", response_model=list[ContextInfo])
def contexts(request: Request):
    return service(request).listContexts()


@router.post("", response_model=InvestigationSummary)
def create(payload: InvestigationCreate, request: Request):
    found, owner = service(request), library_owner(request)
    investigation = call(found.create, owner, payload)
    return found.view(owner, investigation)


@router.get("", response_model=list[InvestigationSummary])
def listInvestigations(request: Request):
    return service(request).list(library_owner(request))


@router.get("/{investigation}", response_model=InvestigationView)
def view(investigation: str, request: Request):
    return call(service(request).view, library_owner(request), investigation)


@router.post("/{investigation}/start", response_model=InvestigationView)
def start(investigation: str, payload: StartRequest, request: Request):
    found, owner = service(request), library_owner(request)
    call(found.start, owner, investigation, payload, consent(request))
    return found.view(owner, investigation)


@router.post("/{investigation}/cancel", response_model=InvestigationView)
def cancel(investigation: str, request: Request):
    found, owner = service(request), library_owner(request)
    call(found.cancel, owner, investigation)
    return found.view(owner, investigation)


@router.post("/{investigation}/resume", response_model=InvestigationView)
def resume(investigation: str, request: Request):
    found, owner = service(request), library_owner(request)
    call(found.resume, owner, investigation)
    return found.view(owner, investigation)


@router.post("/{investigation}/reduce", response_model=InvestigationView)
def reduceFailure(investigation: str, payload: ReduceRequest, request: Request):
    found, owner = service(request), library_owner(request)
    call(found.reduce, owner, investigation, payload)
    return found.view(owner, investigation)


@router.post("/{investigation}/remedies", response_model=InvestigationView)
def remedy(investigation: str, payload: RemedyRequest, request: Request):
    found, owner = service(request), library_owner(request)
    call(found.remedy, owner, investigation, payload)
    return found.view(owner, investigation)


@router.post("/{investigation}/results/{attempt}/replay", response_model=ReplayCheck)
def replay(investigation: str, attempt: str, request: Request):
    return call(service(request).replay, library_owner(request), investigation, attempt)


@router.get("/{investigation}/export")
def export(investigation: str, request: Request):
    return call(service(request).export, library_owner(request), investigation)


@router.get("/{investigation}/public-export")
def publicExport(investigation: str, request: Request):
    return call(service(request).publicExport, library_owner(request), investigation)
