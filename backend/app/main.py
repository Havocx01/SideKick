"""The FastAPI application."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import routes_copilot, routes_evidence, routes_experiments
from app.config import get_settings
from app.utils.logging_setup import get_logger, setup_logging

logger = get_logger(__name__)

DESCRIPTION = """\
Sidekick selects failure-prediction models by how their alerts survive sensor faults.

In local full mode, upload or generate data, confirm its mapping, and launch a
bounded worker experiment. Each experiment stores its own data fingerprint,
configuration, partitions, source identifiers and results. Replay mode serves the
committed benchmark and rejects upload and training requests. Both modes provide
comparison, warning replay, a deterministic Evidence guide and evidence exports.
No external language model or API key is required.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = get_settings()
    logger.info("starting Sidekick %s in %s mode", __version__, settings.mode)
    if settings.mode == "full":
        settings.ensure_dirs()
        from app.experiments.jobs import Jobs

        app.state.jobs = Jobs(settings.artifacts_dir / "workspace")
    logger.info("Evidence guide uses recorded metrics; external model calls are disabled")
    # Warm the bundle so a cold start pays the parse cost before the first request.
    try:
        from app.api.deps import _cached_bundle

        _cached_bundle()
    except FileNotFoundError:
        logger.warning(
            "no evidence bundle found at %s; evidence routes will return 503 until one is generated",
            settings.bundle_path,
        )
    try:
        yield
    finally:
        if settings.mode == "full":
            app.state.jobs.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Sidekick", version=__version__, description=DESCRIPTION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins) or ["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(routes_evidence.router)
    app.include_router(routes_copilot.router)
    app.include_router(routes_experiments.router)

    if not _mount_frontend(app, settings.static_dir):

        @app.get("/", include_in_schema=False)
        def root() -> JSONResponse:
            return JSONResponse(
                {
                    "name": "Sidekick",
                    "version": __version__,
                    "mode": settings.mode,
                    "docs": "/docs",
                    "health": "/api/health",
                    "note": (
                        "No built frontend found. Run the Vite dev server, or build it "
                        "into frontend/dist to have this service serve it."
                    ),
                }
            )

    return app


def _mount_frontend(app: FastAPI, directory: Path) -> bool:
    index = directory / "index.html"
    if not index.is_file():
        return False

    assets = directory / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")
        candidate = (directory / path).resolve()
        if path and candidate.is_file() and directory.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)

    logger.info("serving the built frontend from %s", directory)
    return True


app = create_app()
