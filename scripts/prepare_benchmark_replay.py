"""Reconstruct bounded benchmark traces only after matching original required metrics."""

import hashlib
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import ExperimentConfig
from app.data.loader import load_dataset
from app.evidence.bundle import _build_replay, load_bundle
from app.faults.runner import run_matrix, score_clean, to_scenario_results
from app.models.candidates import candidate_grid
from app.models.train import train_development
from app.utils.jsonio import write_json


def main():
    path = ROOT / "evidence" / "bundle.json"
    original = load_bundle(path)
    config = ExperimentConfig(**original.config)
    dataset = load_dataset("cmapss", subset="FD001", config=config)
    current_data_hash = dataset.data_hash
    if dataset.data_hash != original.profile.data_hash:
        # Revision 2 used readings and cycle IDs, before target/mapping fingerprints.
        legacy = hashlib.sha256()
        legacy.update("|".join(dataset.sensors).encode())
        legacy.update(np.ascontiguousarray(dataset.frame[dataset.sensors].to_numpy(dtype=np.float64)).tobytes())
        legacy.update(dataset.frame.equipment_id.astype(str).str.cat(sep="\x1f").encode())
        legacy.update(np.ascontiguousarray(dataset.frame.cycle.to_numpy(dtype=np.int64)).tobytes())
        if config.protocol_revision != 2 or legacy.hexdigest()[:16] != original.profile.data_hash:
            raise ValueError("Benchmark dataset hash differs; do not supplement these results.")
        dataset = replace(dataset, data_hash=original.profile.data_hash)
    # Historical tree weights are unavailable; only verified lr2 is supplemented.
    templates = [c for c in candidate_grid(config) if c.config_id == "lr2"]
    training = train_development(dataset, config=config, splits=original.splits, candidates=templates)
    thresholds = {f"{v.candidate.value}/{v.config_id}": v.threshold for v in original.development_selection.ranked if v.config_id == "lr2"}
    faults = {r.scenario_id: r.fault for r in original.scenario_results if r.required}
    matrix = run_matrix(training, list(faults.values()), thresholds, config=config)
    clean = score_clean(training, thresholds, config=config)
    result = SimpleNamespace(training=training, matrix=matrix, thresholds=thresholds, selection=original.development_selection,
        scenario_results=to_scenario_results(matrix, training, thresholds, clean, required_ids=set(faults)))
    if result.training.splits.development != original.splits.development or result.training.splits.holdout != original.splits.holdout:
        raise ValueError("Original equipment split was not reproduced.")
    measured = {(r.candidate, r.config_id, r.scenario_id): r for r in result.scenario_results}
    compared = 0
    for old in original.scenario_results:
        if old.config_id != "lr2":
            continue
        if not old.required and old.scenario_id != "clean":
            continue
        new = measured[(old.candidate, old.config_id, old.scenario_id)]
        if abs(old.threshold - new.threshold) > 1e-9:
            raise ValueError("Original threshold was not reproduced.")
        for name, value in old.metrics.model_dump().items():
            if name == "detection_ci":
                continue
            actual = getattr(new.metrics, name)
            if value is None and actual is None:
                continue
            if value is None or actual is None or abs(value - actual) > 1e-9:
                raise ValueError(f"Original metric differs: {old.config_id}/{old.scenario_id}/{name}: {value} versus {actual}")
            compared += 1
    traces = []
    for verdict in result.selection.ranked:
        if verdict.config_id != "lr2":
            continue
        name = f"{verdict.candidate.value}/{verdict.config_id}"
        for trace in _build_replay(result, name, result.thresholds[name], 3, None, config):
            trace.representative_reason = f"Verified reconstruction: {trace.representative_reason}. Selected example, not fleet-wide performance."
            traces.append(trace.model_dump(mode="json"))
    write_json(path.parent / "replays-v1.5.json", {
        "original_bundle_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "current_dataset_fingerprint": current_data_hash,
        "metrics_compared": compared, "tolerance": 1e-9,
        "note": "Supplemental replay reconstruction. Original metrics, model seeds and protocol remain unchanged.",
        "replay_series": traces,
    })
    print(f"Verified {compared} metrics; saved {len(traces)} bounded replays.")


if __name__ == "__main__":
    main()
