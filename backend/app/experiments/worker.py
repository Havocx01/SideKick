"""Subprocess entry point; ML imports never run in the replay service."""

from __future__ import annotations

import os
import sys
import threading
import time
import traceback
from pathlib import Path

from app.experiments.store import Workspace


def run(root: Path, id: str):
    workspace = Workspace(root)
    directory = workspace.directory("experiments", id)

    def watch_parent():
        while True:
            time.sleep(2)
            if not workspace.alive(id):
                os._exit(2)  # Do not leave a training process after an unclean server exit.

    threading.Thread(target=watch_parent, daemon=True).start()
    try:
        from app.config import ExperimentConfig
        from app.evidence.bundle import build_bundle, write_bundle
        from app.evidence.store import EvidenceStore
        from app.experiments.datasets import validated_dataset
        from app.experiments.provenance import source_digest
        from app.schemas import ColumnMapping
        from app.scoring.pipeline import evaluate

        record = workspace.get("experiments", id)
        registration = workspace.get("datasets", record["dataset_id"])
        config = ExperimentConfig(**record["config"])
        config.validate()
        if source_digest() != record["source_digest"]:
            raise ValueError(
                "Source files changed after this run was queued. Start a new experiment with the current code."
            )

        def progress(stage, completed=0, total=None, unit=""):
            workspace.update(id, stage=stage, completed_work=completed, total_work=total, work_unit=unit)

        progress("validating")
        mapping = ColumnMapping.model_validate(registration["mapping"])
        dataset = validated_dataset(
            workspace.directory("datasets", record["dataset_id"]) / "data.csv",
            mapping,
            registration["complete_histories"],
            id=record["dataset_id"],
            source=record["source"],
            config=config,
        )
        if dataset.data_hash != record["data_hash"]:
            raise ValueError("Dataset contents changed after confirmation. Upload and confirm it again.")
        evidence = EvidenceStore(directory / "runs")
        training = evidence.start_run(
            "training",
            config=config,
            data_hash=dataset.data_hash,
            params={
                "source_digest": record["source_digest"],
                "experiment_id": id,
                "fault_set": "required",
                "complete_histories": registration["complete_histories"],
                "mapping": mapping.model_dump(),
            },
        )
        result = evaluate(dataset, config=config, include_full_matrix=False, progress=progress)
        evidence.log_metrics(
            training,
            {
                "candidates": float(len(result.selection.ranked)),
                "development_engines": float(len(result.training.splits.development)),
            },
        )
        for verdict in result.selection.ranked:
            run = evidence.start_run(
                "fault_matrix",
                config=config,
                data_hash=dataset.data_hash,
                parent_run_id=training.run_id,
                params={
                    "candidate": verdict.candidate.value,
                    "config_id": verdict.config_id,
                    "threshold": verdict.threshold,
                    "source_digest": record["source_digest"],
                },
            )
            evidence.log_metrics(
                run,
                {
                    "clean_detection_fraction": verdict.clean.detection_fraction,
                    "clean_early_alarm_burden": verdict.clean.early_alarm_burden,
                    "required_mean_detection": verdict.mean_detection_required,
                    "required_worst_detection": verdict.worst_detection_required,
                    "qualifies": float(verdict.qualifies),
                },
            )
            for scenario in result.scenario_results:
                if scenario.candidate == verdict.candidate and scenario.config_id == verdict.config_id:
                    scenario.run_id = run.run_id
        evidence.start_run(
            "selection",
            config=config,
            data_hash=dataset.data_hash,
            parent_run_id=training.run_id,
            params={
                "outcome": result.selection.outcome.value,
                "criteria": result.criteria.model_dump(),
                "source_digest": record["source_digest"],
            },
        )
        progress("preparing results")
        bundle = build_bundle(result, config=config, runs=evidence.list_runs())
        bundle.schema_version = 2
        bundle.experiment_id = id
        bundle.dataset_id = record["dataset_id"]
        bundle.source_digest = record["source_digest"]
        bundle.confirmed_mapping = mapping
        bundle.complete_histories_confirmed = registration["complete_histories"]
        bundle.holdout_status = "Reserved equipment was not scored. No automatic holdout evaluation is performed."
        bundle.limitations = [
            "Synthetic demonstration data does not establish performance on real equipment."
            if record["source"] == "synthetic"
            else "These uploaded histories have not been independently validated as representative of field equipment.",
            "Development results support comparison, not automatic deployment approval. Reserved equipment was not scored.",
            "Required injected sensor faults are simulated; their severities are not calibrated to ABB field measurements.",
            "The comparison uses complete run-to-failure histories only. It does not establish performance on censored histories or live equipment.",
            "Small differences and overlapping confidence intervals do not establish a reliable ranking or a causal benefit from augmentation.",
            "Attributions describe changes in model scores, not the physical cause of a failure.",
        ]
        if record["name"] == "Hosted sample: 30 histories, 3 sensors":
            bundle.limitations.insert(
                0,
                "The hosted sample uses 30 short synthetic histories, three sensors and one configuration per model family to fit free hosting. Only ten histories are evaluated across five folds; twenty remain unscored. It demonstrates the workflow and is not comparable to the broader local sample or NASA benchmark.",
            )
        if source_digest() != record["source_digest"]:
            raise ValueError(
                "Source files changed during training. This run cannot claim a single source version; rerun after edits finish."
            )
        temporary = directory / "bundle.pending.json"
        write_bundle(bundle, temporary)
        temporary.replace(directory / "bundle.json")
        progress("preparing results", 1, 1, "evidence bundle written")
    except Exception as exc:
        (directory / "error.txt").write_text(str(exc), encoding="utf-8")
        traceback.print_exc()
        raise


if __name__ == "__main__":
    run(Path(sys.argv[1]), sys.argv[2])
