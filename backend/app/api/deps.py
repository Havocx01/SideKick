"""Shared API dependencies.

The bundle is loaded once and cached. On the hosted service it is a committed file
that never changes during a process's life, so a cache is both safe and the reason
the service fits in 512 MB: no model, no dataset, no training library.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import HTTPException

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


def bundle() -> EvidenceBundle:
    try:
        return _cached_bundle()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "No evidence bundle is available. Generate one locally with "
                "'python scripts/run_pipeline.py'."
            ),
        ) from exc


@lru_cache(maxsize=1)
def _cached_registry() -> ToolRegistry:
    return ToolRegistry(_cached_bundle(), allow_training=get_settings().mode == "full")


def registry() -> ToolRegistry:
    bundle()  # surface a missing bundle as 503 before building the registry
    return _cached_registry()


def settings() -> Settings:
    return get_settings()
