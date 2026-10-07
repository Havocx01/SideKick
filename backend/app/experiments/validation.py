"""Local frozen-model fitting and one-time reserved-equipment evaluation."""

import hashlib
import importlib.metadata
import json
import time

from app import __version__
from app.config import ExperimentConfig
from app.experiments.provenance import source_digest
from app.schemas import ColumnMapping, FaultScenario, Partition, ScenarioResult

DEPENDENCIES = ("numpy", "pandas", "scikit-learn", "xgboost", "joblib")


def dependency_versions():
    versions = {}
    for name in DEPENDENCIES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            if name != "xgboost":
                raise
            versions[name] = importlib.metadata.version("xgboost-cpu")
    return versions


def file_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_operation(workspace, record):
    from app.evidence.bundle import load_bundle
    from app.experiments.datasets import validated_dataset
    from app.experiments.exposure import history_ids, seed_known_exposure

    parent_id = record["parent_experiment_id"]
    parent = workspace.get("experiments", parent_id)
    directory = workspace.directory("experiments", record["experiment_id"])
    bundle = load_bundle(workspace.directory("experiments", parent_id) / "bundle.json")
    registration = workspace.get("datasets", record["dataset_id"])
    config = ExperimentConfig(**record["config"])
    config.validate()
    if source_digest() != record["source_digest"] or parent["source_digest"] != record["source_digest"]:
        raise ValueError("Source changed after development. Start a new experiment.")
    workspace.update(record["experiment_id"], stage="validating")
    dataset = validated_dataset(workspace.directory("datasets", record["dataset_id"]) / "data.csv",
        ColumnMapping.model_validate(registration["mapping"]), registration["complete_histories"],
        id=record["dataset_id"], source=record["source"], config=config)
    if dataset.data_hash != record["data_hash"] or bundle.config_fingerprint != record["config_fingerprint"]:
        raise ValueError("Dataset or protocol changed after development.")
    if record["job_kind"] == "freeze":
        freeze(workspace, record, bundle, dataset, config, directory)
    else:
        seed_known_exposure(workspace)
        frozen = workspace.operation(parent_id, "freeze")
        if not frozen or frozen["status"] != "completed":
            raise ValueError("The frozen model is unavailable.")
        artifact = workspace.directory("experiments", frozen["job_id"]) / "model.joblib"
        manifest = frozen["manifest"]
        manifest_path = workspace.directory("experiments", frozen["job_id"]) / "manifest.json"
        if file_digest(manifest_path) != frozen["manifest_digest"] or json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
            raise ValueError("The frozen model manifest changed.")
        if file_digest(artifact) != frozen["artifact_digest"]:
            raise ValueError("The frozen model artifact changed.")
        if manifest["dependency_versions"] != dependency_versions():
            raise ValueError("Dependency versions changed after freezing. Start a new experiment.")
        if manifest["source_digest"] != source_digest() or manifest["data_hash"] != dataset.data_hash:
            raise ValueError("Frozen model provenance no longer matches the data or code.")
        if manifest["splits"] != bundle.splits.model_dump(mode="json"):
            raise ValueError("Equipment assignments changed after freezing.")
        import joblib

        models = joblib.load(artifact)  # Only this backend creates these local artifacts.
        histories = history_ids(dataset, bundle.splits.holdout)
        if not workspace.alive(record["experiment_id"]):
            raise ValueError("Validation was cancelled before scoring.")
        workspace.expose(histories.values(), parent_id, "Final validation began",
                         validation_id=record["operation_id"])
        validate(workspace, record, bundle, dataset, config, models, manifest, directory)
    if source_digest() != record["source_digest"]:
        raise ValueError("Source changed during this job. The result cannot claim one source version.")
    (directory / "result.json").write_text(json.dumps({"operation_id": record["operation_id"]}), encoding="utf-8")


def freeze(workspace, record, bundle, dataset, config, directory):
    import joblib
    import numpy as np

    from app.models.candidates import candidate_grid
    from app.models.design import design_from_blocks, engine_blocks
    from app.models.train import fit_final

    selected = bundle.development_selection.recommended
    if bundle.dependency_versions != dependency_versions():
        raise ValueError("Dependency versions changed after development. Start a new experiment.")
    selected_name = f"{selected.candidate.value}/{selected.config_id}"
    baseline = next(v for v in bundle.development_selection.ranked if v.candidate.value == "age_baseline")
    names = list(dict.fromkeys((selected_name, f"age_baseline/{baseline.config_id}")))
    grid = {candidate.name: candidate for candidate in candidate_grid(config)}
    models, sample_scores = {}, {}
    workspace.update(record["experiment_id"], stage="refitting selected model", total_work=len(names), work_unit="models fitted")
    for i, name in enumerate(names):
        fitted, builder, _ = fit_final(dataset, bundle.splits, grid[name], config=config)
        first_id = bundle.splits.development[0]
        sample = dataset.subset([first_id])
        blocks = engine_blocks(sample, builder)
        design = design_from_blocks(blocks, builder.feature_names())
        sample_scores[name] = fitted.score(design)
        models[name] = (fitted, builder)
        workspace.update(record["experiment_id"], completed_work=i + 1)
    workspace.update(record["experiment_id"], stage="preparing frozen model")
    path = directory / "model.joblib"
    joblib.dump(models, path, compress=3)
    restored = joblib.load(path)
    for name, (fitted, builder) in restored.items():
        sample = dataset.subset([bundle.splits.development[0]])
        design = design_from_blocks(engine_blocks(sample, builder), builder.feature_names())
        if not np.array_equal(sample_scores[name], fitted.score(design)):
            raise ValueError("Frozen model serialization did not reproduce development scores.")
    thresholds = {f"{v.candidate.value}/{v.config_id}": v.threshold for v in bundle.development_selection.ranked}
    manifest = {"release": __version__, "candidate": selected_name, "thresholds": {n: thresholds[n] for n in names},
                "candidate_parameters": {n: models[n][0].params for n in names}, "config": config.as_dict(),
                "config_fingerprint": bundle.config_fingerprint, "data_hash": dataset.data_hash,
                "dataset_id": record["dataset_id"], "splits": bundle.splits.model_dump(mode="json"),
                "mapping": bundle.confirmed_mapping.model_dump(), "protocol": bundle.protocol.model_dump(),
                "source_digest": record["source_digest"], "git_commit": bundle.git_commit,
                "dependency_versions": dependency_versions(), "frozen_at": time.time()}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    workspace.update_operation(record["operation_id"], manifest=manifest, artifact_digest=file_digest(path),
                               manifest_digest=file_digest(directory / "manifest.json"))


def score_model(candidate, builder, dataset, threshold, scenarios, required_ids, config, progress):
    from app.faults.inject import apply_fault
    from app.models.design import EngineBlock, design_from_blocks, engine_blocks
    from app.scoring.metrics import aggregate, score_engine

    blocks = engine_blocks(dataset, builder)
    feature_names = builder.feature_names()
    equipment = sorted(blocks)
    clean_design = design_from_blocks(blocks, feature_names)
    scores = candidate.score(clean_design)
    clean = aggregate([score_engine(e, scores[clean_design.equipment_id == e],
        clean_design.cycle[clean_design.equipment_id == e], clean_design.rul[clean_design.equipment_id == e],
        threshold, config=config) for e in equipment], config=config)
    results, per_case = [], {}
    for i, spec in enumerate(scenarios):
        scorings, skipped = [], []
        for e in equipment:
            block = blocks[e]
            readings = dataset.sensor_matrix(e)[:, builder.preprocessor.index_of(spec.sensor)]
            injected = apply_fault(readings, block.rul, spec, sensor_std=builder.preprocessor.std_of(spec.sensor), config=config)
            if not injected.applied:
                skipped.append(f"{e}: {injected.reason}")
                continue
            features = block.features.copy()
            builder.rebuild_sensor(features, injected.values, spec.sensor)
            faulted = EngineBlock(e, features, block.labels, block.cycles, block.rul, block.rows, block.scorable)
            design = design_from_blocks({e: faulted}, feature_names)
            scorings.append(score_engine(e, candidate.score(design), design.cycle, design.rul, threshold, config=config))
        results.append(ScenarioResult(scenario_id=spec.scenario_id, candidate=candidate.kind, config_id=candidate.config_id,
            partition=Partition.holdout, threshold=threshold, fault=spec, metrics=aggregate(scorings, config=config),
            required=spec.scenario_id in required_ids, expected_engines=len(equipment),
            coverage_complete=len(scorings) == len(equipment), coverage_notes=skipped))
        per_case[spec.scenario_id] = scorings
        progress(i + 1, len(scenarios))
    return clean, results, blocks, per_case


def validate(workspace, record, bundle, dataset, config, models, manifest, directory):
    from app.evidence.replay import build_fitted_series
    from app.scoring.selection import build_verdict, select

    entries = [FaultScenario.model_validate(s) for s in config.fault_scenarios]
    specs = [s.fault for s in entries]
    required_ids = {s.fault.scenario_id for s in entries if s.required}
    held_back = dataset.subset(bundle.splits.holdout)
    verdicts, rows, traces = [], [], {}
    selected_name = manifest["candidate"]
    ordered = [selected_name] + [n for n in models if n != selected_name]
    for model_index, name in enumerate(ordered):
        candidate, builder = models[name]
        threshold = manifest["thresholds"][name]

        def progress(done, total, model_index=model_index):
            workspace.update(record["experiment_id"], stage="testing reserved equipment",
                completed_work=model_index * total + done, total_work=len(ordered) * total, work_unit="model-scenario tests completed")

        clean, faulted, blocks, per_case = score_model(candidate, builder, held_back, threshold, specs, required_ids, config, progress)
        verdict = build_verdict(candidate=candidate.kind, config_id=candidate.config_id, threshold=threshold,
            clean=clean, required=[r for r in faulted if r.required], criteria=bundle.development_selection.criteria)
        verdicts.append(verdict)
        rows.append(ScenarioResult(scenario_id="clean", candidate=candidate.kind, config_id=candidate.config_id,
            partition=Partition.holdout, threshold=threshold, metrics=clean, expected_engines=len(bundle.splits.holdout), coverage_complete=True))
        rows.extend(faulted)
        targets = {verdict.worst_scenario_id: "Weakest detection", verdict.worst_burden_scenario_id: "Highest alarm burden"}
        for scenario_id, reason in targets.items():
            spec = next((s for s in specs if s.scenario_id == scenario_id), None)
            if spec is None:
                continue
            scorings = per_case[scenario_id]
            if reason == "Weakest detection":
                examples = sorted(scorings, key=lambda s: (not s.outcome.missed, not s.outcome.late, s.outcome.equipment_id))[:3]
            else:
                examples = sorted(scorings, key=lambda s: (-s.alarm_eligible_cycles / max(1, s.eligible_cycles), s.outcome.equipment_id))[:3]
            for scoring in examples:
                e = scoring.outcome.equipment_id
                for fault in (None, spec):
                    trace = build_fitted_series(held_back, builder, candidate, blocks[e], e, threshold, spec=fault, config=config)
                    if trace:
                        trace.partition = Partition.holdout
                        trace.representative_reason = reason
                        traces[(name, e, trace.scenario_id)] = trace
    selection = select([verdicts[0]], bundle.development_selection.criteria, partition=Partition.holdout)
    selection.ranked.extend(verdicts[1:])
    selection.notes.append("The age baseline is a frozen reference. Final results do not select a replacement or retune the model.")
    payload = {"selection": selection.model_dump(mode="json"), "scenario_results": [r.model_dump(mode="json") for r in rows],
               "replay_series": [r.model_dump(mode="json") for r in traces.values()]}
    (directory / "validation.pending.json").write_text(json.dumps(payload, allow_nan=False), encoding="utf-8")
    (directory / "validation.pending.json").replace(directory / "validation.json")
