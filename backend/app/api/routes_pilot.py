"""Pilot declarations and engineer decisions are available only in the local workspace."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import bundle
from app.api.routes_experiments import upload_jobs
from app.experiments import pilot
from app.experiments.jobs import Jobs
from app.schemas import EvidenceBundle, PilotAgreementCreate, PilotAgreementRecord, PilotOutcomeCreate, PilotOutcomeRecord, PilotState

router = APIRouter(prefix="/api/experiments/{experiment_id}/pilot", tags=["pilot"])


@router.get("", response_model=PilotState)
def pilot_state(jobs: Jobs = Depends(upload_jobs), loaded: EvidenceBundle = Depends(bundle)):
    return pilot.state(jobs.workspace, loaded)


@router.post("/agreement", response_model=PilotAgreementRecord, status_code=201)
def agree_pilot(payload: PilotAgreementCreate, jobs: Jobs = Depends(upload_jobs), loaded: EvidenceBundle = Depends(bundle)):
    try:
        return pilot.agree(jobs.workspace, loaded, payload)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.post("/review", response_model=PilotOutcomeRecord, status_code=201)
def record_review(payload: PilotOutcomeCreate, jobs: Jobs = Depends(upload_jobs), loaded: EvidenceBundle = Depends(bundle)):
    try:
        return pilot.review(jobs.workspace, loaded, payload)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
