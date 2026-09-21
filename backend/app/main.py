"""The FastAPI application.

Two deployment shapes, one codebase:

``SIDEKICK_MODE=full``     Local. The full pipeline is importable and the evidence
                           store on disk is readable.
``SIDEKICK_MODE=replay``   Hosted. Serves the committed evidence bundle only. No
                           training library is installed, no model is loaded and
                           nothing is written to disk, because the free tier has
                           512 MB of memory and an ephemeral filesystem.

The distinction is visible at ``/api/health`` rather than hidden, so nobody
mistakes the hosted demo for a live training service.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import routes_copilot, routes_evidence
from app.config import get_settings
from app.utils.logging_setup import get_logger, setup_logging

logger = get_logger(__name__)

DESCRIPTION = """\
Sidekick selects failure-prediction models by how their alerts survive sensor faults.

This API serves recorded evidence: a dataset profile, engine-level partitions, every
scenario result with its confidence interval, the selection verdict, calibration
reports and per-engine replay series. Nothing here computes a metric; the pipeline
that produced them runs locally and records every result with the data hash,
partitions, seeds and configuration that produced it.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = get_settings()
    logger.info("starting Sidekick %s in %s mode", __version__, settings.mode)
    if settings.mode == "full":
        settings.ensure_dirs()
    if not settings.llm_available:
        logger.info("no OPENAI_API_KEY: the copilot will answer from recorded evidence")
    # Warm the bundle so a cold start pays the parse cost before the first request.
    try:
        from app.api.deps import _cached_bundle

        _cached_bundle()
    except FileNotFoundError:
        logger.warning(
            "no evidence bundle found at %s; evidence routes will return 503 until one "
            "is generated",
            settings.bundle_path,
        )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Sidekick",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins) or ["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(routes_evidence.router)
    app.include_router(routes_copilot.router)

    @app.get("/", include_in_schema=False)
    def root() -> JSONResponse:
        return JSONResponse(
            {
                "name": "Sidekick",
                "version": __version__,
                "mode": settings.mode,
                "docs": "/docs",
                "health": "/api/health",
            }
        )

    return app


app = create_app()
