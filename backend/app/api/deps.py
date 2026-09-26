"""Shared API dependencies."""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, HTTPException, Request

from app.config import Settings, get_settings
from app.copilot.tools import ToolRegistry
from app.evidence.bundle import load_bundle
from app.schemas import EvidenceBundle
from app.utils.logging_setup import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _cached_bundle() -> EvidenceBundle:
    settings = get_settings()
    bundle = load_bundle(settings.bundle_path)
    logger.info(
        "loaded evidence bundle: %s, %d scenario results, config %s",
        bundle.profile.dataset_id,
        len(bundle.scenario_results),
        bundle.config_fingerprint,
    )
    return bundle


def reload_bundle() -> None:
    """Drop the cache, so a regenerated bundle is picked up without a restart."""
    _cached_bundle.cache_clear()
    _cached_registry.cache_clear()


def bundle(request: Request, experiment_id: str | None = None) -> EvidenceBundle:
    if experiment_id:
        if get_settings().mode != "full":
            raise HTTPException(403, "Local experiments are unavailable in replay mode.")
        try:
            workspace = request.app.state.jobs.workspace
            record = workspace.get("experiments", experiment_id)
            if record["status"] != "completed":
                raise HTTPException(409, "This experiment has no completed results yet.")
            return load_bundle(workspace.directory("experiments", experiment_id) / "bundle.json")
        except (KeyError, ValueError):
            raise HTTPException(404, "Experiment not found") from None
    try:
        return _cached_bundle()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=("No evidence bundle is available. Generate one locally with 'python scripts/run_pipeline.py'."),
        ) from exc


@lru_cache(maxsize=1)
def _cached_registry() -> ToolRegistry:
    return ToolRegistry(_cached_bundle(), allow_training=get_settings().mode == "full")


def registry(loaded: EvidenceBundle = Depends(bundle)) -> ToolRegistry:
    return ToolRegistry(loaded, allow_training=False)


def settings() -> Settings:
    return get_settings()
