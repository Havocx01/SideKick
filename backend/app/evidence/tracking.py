"""Optional MLflow mirror."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import get_settings
from app.schemas import RunRecord
from app.utils.logging_setup import get_logger

logger = get_logger(__name__)

EXPERIMENT_NAME = "sidekick-fault-robustness"

_warned = False


def _mlflow() -> Any | None:
    global _warned
    settings = get_settings()
    if not settings.mlflow_enabled:
        return None
    try:
        import mlflow
    except ImportError:
        if not _warned:
            logger.info(
                "MLflow is not installed; run records are still written to the "
                "evidence store. Install backend/requirements-full.txt for the UI."
            )
            _warned = True
        return None
    mlflow.set_tracking_uri(settings.mlflow_uri)
    mlflow.set_experiment(EXPERIMENT_NAME)
    return mlflow


def mirror_run(record: RunRecord, *, artifacts: dict[str, Path] | None = None) -> str | None:
    mlflow = _mlflow()
    if mlflow is None:
        return None

    try:
        with mlflow.start_run(run_name=record.run_id) as active:
            mlflow.set_tags(
                {
                    "sidekick.run_id": record.run_id,
                    "sidekick.kind": record.kind,
                    "sidekick.config_fingerprint": record.config_fingerprint,
                    "sidekick.data_hash": record.data_hash or "",
                    "sidekick.git_commit": record.git_commit or "",
                }
            )
            mlflow.log_params(_flatten(record.params))
            if record.seed is not None:
                mlflow.log_param("seed", record.seed)
            mlflow.log_metrics({k: float(v) for k, v in record.metrics.items()})
            for name, path in (artifacts or {}).items():
                if Path(path).exists():
                    mlflow.log_artifact(str(path), artifact_path=name)
            return active.info.run_id
    except Exception as exc:  # pragma: no cover - tracking must never break a run
        logger.warning("MLflow mirroring failed, continuing without it: %s", exc)
        return None


def _flatten(params: dict, prefix: str = "", limit: int = 100) -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in params.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{name}.", limit))
        elif isinstance(value, (list, tuple)):
            flat[name] = ",".join(str(v) for v in value)[:250]
        else:
            flat[name] = str(value)[:250]
        if len(flat) >= limit:
            break
    return flat
