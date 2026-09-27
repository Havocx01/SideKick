"""Browser experiments, guarded before data preparation or worker launch."""

from urllib.parse import unquote
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app.api.deps import bundle
from app.config import get_settings
from app.experiments.decision import decision
from app.experiments.export import export_zip
from app.experiments.jobs import Jobs
from app.experiments.demo import owner, public_origin
from app.experiments.store import ACTIVE
from app.schemas import (
    DatasetConfirmation,
    DatasetRegistration,
    DecisionReport,
    EvidenceBundle,
    ExperimentCreate,
    ExperimentRecord,
)

router = APIRouter(prefix="/api", tags=["experiments"])


def local_jobs(request: Request) -> Jobs:
    if get_settings().mode == "replay":
        raise HTTPException(
            403, "This deployment explores recorded evidence only. Run Sidekick locally to upload data or train models."
        )
    origin = request.headers.get("origin")
    if request.method == "POST" and origin and origin not in (*get_settings().cors_origins, public_origin(request)):
        raise HTTPException(403, "Local experiment changes must come from the Sidekick interface.")
    jobs = getattr(request.app.state, "jobs", None)
    if jobs is None:
        raise HTTPException(503, "The local workspace is not ready.")
    return jobs


def check_access(request: Request, kind: str, id: str):
    if get_settings().mode == "demo":
        request.app.state.demo.require(kind, id, owner(request))


def upload_jobs(request: Request) -> Jobs:
    if get_settings().mode != "full":
        raise HTTPException(403, "CSV uploads are available locally. Use the synthetic sample in the hosted demo.")
    return local_jobs(request)


@router.post("/datasets/sample", response_model=DatasetRegistration)
def sample_dataset(request: Request, jobs: Jobs = Depends(local_jobs)):
    from app.experiments.datasets import sample

    if get_settings().mode == "demo":
        return request.app.state.demo.sample(owner(request))
    return sample(jobs.workspace)


@router.post("/datasets/upload", response_model=DatasetRegistration)
async def upload(request: Request, jobs: Jobs = Depends(upload_jobs)):
    # Stream the raw CSV body, enforcing the limit before parsing or storing it.
    # This avoids unbounded multipart parsing before the replay-mode guard.
    from app.experiments.datasets import MAX_UPLOAD_BYTES, register

    id = str(uuid4())
    directory = jobs.workspace.directory("datasets", id)
    directory.mkdir(parents=True)
    path = directory / "data.csv"
    size = 0
    try:
        with path.open("wb") as output:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "CSV files must be 10 MB or smaller.")
                output.write(chunk)
        return register(jobs.workspace, path, id, unquote(request.headers.get("x-filename", "Uploaded CSV")))
    except HTTPException:
        path.unlink(missing_ok=True)
        raise
    except (ValueError, UnicodeError) as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(422, f"Cannot read this CSV. {exc}") from exc


@router.get("/datasets/{dataset_id}", response_model=DatasetRegistration)
def dataset(dataset_id: str, request: Request, jobs: Jobs = Depends(local_jobs)):
    check_access(request, "datasets", dataset_id)
    try:
        return jobs.workspace.get("datasets", dataset_id)
    except (KeyError, ValueError):
        raise HTTPException(404, "Dataset not found") from None


@router.post("/datasets/{dataset_id}/confirm", response_model=DatasetRegistration)
def confirm_dataset(dataset_id: str, payload: DatasetConfirmation, request: Request, jobs: Jobs = Depends(local_jobs)):
    from app.experiments.datasets import confirm

    check_access(request, "datasets", dataset_id)
    if get_settings().mode == "demo":
        raise HTTPException(
            403, "The hosted sample has a fixed, confirmed mapping. Run locally to use a different dataset."
        )
    try:
        return confirm(jobs.workspace, dataset_id, payload)
    except KeyError:
        raise HTTPException(404, "Dataset not found") from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/experiments", response_model=ExperimentRecord, status_code=201)
def create_experiment(payload: ExperimentCreate, request: Request, jobs: Jobs = Depends(local_jobs)):
    check_access(request, "datasets", payload.dataset_id)
    try:
        if get_settings().mode == "demo":
            demo = request.app.state.demo
            with demo.lock:
                if any(record["status"] in ACTIVE for record in jobs.workspace.list()):
                    raise HTTPException(
                        409,
                        "The shared server is running another experiment. Try again shortly, or explore the recorded benchmark.",
                    )
                demo.admit("experiment", owner(request))
                record = jobs.create(payload)
                demo.claim("experiments", record.experiment_id, owner(request))
                return record
        return jobs.create(payload)
    except KeyError:
        raise HTTPException(404, "Dataset not found") from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/experiments", response_model=list[ExperimentRecord])
def experiments(request: Request, jobs: Jobs = Depends(local_jobs)):
    records = jobs.workspace.list()
    if get_settings().mode == "demo":
        ids = request.app.state.demo.ids("experiments", owner(request))
        records = [record for record in records if record["experiment_id"] in ids]
    return records


@router.get("/experiments/{experiment_id}", response_model=ExperimentRecord)
def experiment(experiment_id: str, request: Request, jobs: Jobs = Depends(local_jobs)):
    check_access(request, "experiments", experiment_id)
    for record in jobs.workspace.list():
        if record["experiment_id"] == experiment_id:
            return record
    raise HTTPException(404, "Experiment not found")


@router.post("/experiments/{experiment_id}/cancel", response_model=ExperimentRecord)
def cancel(experiment_id: str, request: Request, jobs: Jobs = Depends(local_jobs)):
    check_access(request, "experiments", experiment_id)
    try:
        jobs.cancel(experiment_id)
        return experiment(experiment_id, request, jobs)
    except (KeyError, ValueError):
        raise HTTPException(404, "Experiment not found") from None


@router.get("/decision", response_model=DecisionReport)
def decision_report(loaded: EvidenceBundle = Depends(bundle)):
    return decision(loaded)


@router.get("/export")
def download(loaded: EvidenceBundle = Depends(bundle)):
    return Response(
        export_zip(loaded),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="sidekick-{loaded.experiment_id or "benchmark"}-evidence.zip"'
        },
    )
