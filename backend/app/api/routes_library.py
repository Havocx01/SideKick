"""Workspace library with the same local/demo access boundary as experiments."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.routes_experiments import local_jobs
from app.config import get_settings
from app.experiments.demo import owner
from app.experiments.jobs import Jobs
from app.experiments.library import Library
from app.schemas import LibraryFolder, LibraryFolderInput, LibrarySnapshot, LibraryUpdate

router = APIRouter(prefix="/api/library", tags=["library"])


def library_scope(request):
    if get_settings().mode == "demo":
        visitor = owner(request)
        demo = request.app.state.demo
        return f"demo:{visitor}", {"run": demo.ids("experiments", visitor), "upload": demo.ids("datasets", visitor)}
    return "local", None


def execute(action):
    try:
        return action()
    except KeyError:
        raise HTTPException(404, "This item or folder is unavailable. Refresh the library and try again.") from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("", response_model=LibrarySnapshot)
def snapshot(request: Request, jobs: Jobs = Depends(local_jobs)):
    scope, allowed = library_scope(request)
    return Library(jobs.workspace).snapshot(scope, allowed)


@router.post("/folders", response_model=LibraryFolder, status_code=201)
def create_folder(payload: LibraryFolderInput, request: Request, jobs: Jobs = Depends(local_jobs)):
    scope, _ = library_scope(request)
    return execute(lambda: Library(jobs.workspace).create_folder(scope, payload.name))


@router.post("/folders/{folder_id}/rename", response_model=LibraryFolder)
def rename_folder(folder_id: UUID, payload: LibraryFolderInput, request: Request, jobs: Jobs = Depends(local_jobs)):
    scope, _ = library_scope(request)
    return execute(lambda: Library(jobs.workspace).rename_folder(scope, str(folder_id), payload.name))


@router.post("/folders/{folder_id}/remove")
def remove_folder(folder_id: UUID, request: Request, jobs: Jobs = Depends(local_jobs)):
    scope, _ = library_scope(request)
    execute(lambda: Library(jobs.workspace).remove_folder(scope, str(folder_id)))
    return {"saved": True}


@router.post("/items")
def change_items(payload: LibraryUpdate, request: Request, jobs: Jobs = Depends(local_jobs)):
    scope, allowed = library_scope(request)
    execute(lambda: Library(jobs.workspace).change(scope, [item.model_dump(mode="json") for item in payload.items], payload.action,
                                                 display_name=payload.display_name,
                                                 folder_id=str(payload.folder_id) if payload.folder_id else None, allowed=allowed))
    return {"saved": True}
