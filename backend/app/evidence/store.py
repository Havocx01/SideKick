"""The evidence store.

Every number the application shows resolves to a run record here. A record holds
the configuration fingerprint, the data hash, the seed, the parameters, the
metrics and the paths to any artifacts, so a claim in a report can be traced to
the run that produced it and that run can be repeated.

Plain JSON files are the source of truth rather than MLflow. Two reasons: the
hosted replay service has no room for a tracking server, and a committed JSON
record stays readable by a reviewer with no tooling. MLflow mirrors these records
for the local experiment UI (see :mod:`app.evidence.tracking`) and is optional.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from app.config import EXPERIMENT, ExperimentConfig, get_settings
from app.schemas import ReproducibilityCheck, RunRecord
from app.utils.jsonio import hash_obj, read_json, write_json
from app.utils.logging_setup import get_logger

logger = get_logger(__name__)

INDEX_NAME = "index.json"


@lru_cache(maxsize=1)
def git_commit() -> str | None:
    """Current commit, recorded so a result can be tied to the code that made it."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = result.stdout.strip()
    return commit or None


class EvidenceStore:
    """Append-only store of run records on the local filesystem."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else get_settings().runs_dir
        self.root.mkdir(parents=True, exist_ok=True)

    # -- writing -----------------------------------------------------------

    def start_run(
        self,
        kind: str,
        *,
        config: ExperimentConfig = EXPERIMENT,
        data_hash: str | None = None,
        seed: int | None = None,
        params: dict | None = None,
        parent_run_id: str | None = None,
        notes: list[str] | None = None,
    ) -> RunRecord:
        """Create a run record. Metrics and artifacts are attached afterwards."""
        created = datetime.now(timezone.utc)
        suffix = hash_obj(
            {
                "kind": kind,
                "created": created.isoformat(),
                "params": params or {},
                "data": data_hash,
            },
            length=6,
        )
        record = RunRecord(
            run_id=f"{created.strftime('%Y%m%dT%H%M%S')}-{kind}-{suffix}",
            kind=kind,  # type: ignore[arg-type]
            created_at=created,
            config_fingerprint=config.fingerprint(),
            data_hash=data_hash,
            seed=seed if seed is not None else config.base_seed,
            git_commit=git_commit(),
            parent_run_id=parent_run_id,
            params=dict(params or {}),
            notes=list(notes or []),
        )
        self.save(record)
        return record

    def save(self, record: RunRecord) -> Path:
        path = self.root / f"{record.run_id}.json"
        write_json(path, record.model_dump(mode="json"))
        self._touch_index(record)
        return path

    def log_metrics(self, record: RunRecord, metrics: dict[str, float]) -> RunRecord:
        record.metrics.update({k: float(v) for k, v in metrics.items() if v is not None})
        self.save(record)
        return record

    def log_artifact(self, record: RunRecord, name: str, path: Path) -> RunRecord:
        record.artifacts[name] = str(path)
        self.save(record)
        return record

    def log_json_artifact(self, record: RunRecord, name: str, payload) -> RunRecord:
        target = self.root / record.run_id / f"{name}.json"
        write_json(target, payload)
        return self.log_artifact(record, name, target)

    # -- reading -----------------------------------------------------------

    def get(self, run_id: str) -> RunRecord:
        path = self.root / f"{run_id}.json"
        if not path.exists():
            raise KeyError(f"no run record {run_id!r}")
        return RunRecord.model_validate(read_json(path))

    def list_runs(self, kind: str | None = None, limit: int | None = None) -> list[RunRecord]:
        records: list[RunRecord] = []
        for path in sorted(self.root.glob("*.json"), reverse=True):
            if path.name == INDEX_NAME:
                continue
            try:
                record = RunRecord.model_validate(read_json(path))
            except Exception as exc:  # pragma: no cover - a corrupt file is not fatal
                logger.warning("skipping unreadable run record %s: %s", path.name, exc)
                continue
            if kind and record.kind != kind:
                continue
            records.append(record)
            if limit and len(records) >= limit:
                break
        return records

    def latest(self, kind: str | None = None) -> RunRecord | None:
        records = self.list_runs(kind=kind, limit=1)
        return records[0] if records else None

    def _touch_index(self, record: RunRecord) -> None:
        """Maintain a small index so listing does not require reading every file."""
        path = self.root / INDEX_NAME
        index = read_json(path) if path.exists() else {"runs": []}
        entries = {entry["run_id"]: entry for entry in index.get("runs", [])}
        entries[record.run_id] = {
            "run_id": record.run_id,
            "kind": record.kind,
            "created_at": record.created_at.isoformat(),
            "config_fingerprint": record.config_fingerprint,
            "data_hash": record.data_hash,
            "metric_count": len(record.metrics),
        }
        write_json(
            path,
            {"runs": sorted(entries.values(), key=lambda e: e["created_at"], reverse=True)},
        )


def compare_runs(
    first: RunRecord, second: RunRecord, *, tolerance: float = 1e-9
) -> ReproducibilityCheck:
    """Check that a repeated run reproduced the original's metrics.

    Compares only metrics present in both. A run that produced fewer metrics is
    not silently treated as reproducing the ones it skipped.
    """
    shared = sorted(set(first.metrics) & set(second.metrics))
    largest = 0.0
    for key in shared:
        difference = abs(float(first.metrics[key]) - float(second.metrics[key]))
        largest = max(largest, difference)

    return ReproducibilityCheck(
        run_id=first.run_id,
        repeat_run_id=second.run_id,
        tolerance=tolerance,
        max_absolute_difference=largest,
        metrics_compared=len(shared),
        reproduced=bool(shared) and largest <= tolerance,
    )
