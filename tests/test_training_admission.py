"""Reject unsupported experiments before reserving or exposing any histories."""

from dataclasses import replace
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from app.config import EXPERIMENT
from app.data.contract import build_dataset
from app.experiments.datasets import validated_dataset
from app.experiments.preflight import check_training_feasibility, validate_histories
from app.experiments.protocol import protocol_config
from app.models.train import sample_augmentation_faults
from app.schemas import ColumnMapping, ExperimentProtocol, ExperimentRecord, FaultScenario, FaultSpec, SplitAssignment


MAPPING = ColumnMapping(equipment_id="id", cycle_index="step", sensors=["sensor"], failure_cycle="failure")


def histories(lives, *, config=EXPERIMENT, constant=False):
    rows = []
    for index, life in enumerate(lives):
        for cycle in range(1, life + 1):
            rows.append({"id": str(index), "step": cycle, "sensor": 1.0 if constant else cycle + index / 100, "failure": life})
    return build_dataset(pd.DataFrame(rows), MAPPING, dataset_id=str(uuid4()), source="test", config=config)


def folds(dataset):
    ids = dataset.equipment_ids
    return SplitAssignment(development=ids, holdout=[], folds=[[id] for id in ids], seed=0, config_fingerprint=dataset.config.fingerprint())


def test_duplicates_use_existing_identity_and_identify_equipment():
    data = histories([100, 100])
    frame = data.frame.copy()
    frame.loc[frame.equipment_id == "1", "sensor"] = frame.loc[frame.equipment_id == "0", "sensor"].to_numpy()
    with pytest.raises(ValueError, match=r"Repeated readings.*0.*1.*independent"):
        validate_histories(replace(data, frame=frame))
    validate_histories(data)


def test_duplicate_confirmation_rejected_before_splitting(tmp_path):
    data = histories([100] * 25)
    frame = data.frame.copy()
    frame["sensor"] = frame["cycle"].astype(float)
    path = tmp_path / "copies.csv"
    frame.to_csv(path, index=False)
    mapping = ColumnMapping(equipment_id="equipment_id", cycle_index="cycle", sensors=["sensor"], failure_cycle="failure_cycle")
    with pytest.raises(ValueError, match="Repeated readings"):
        validated_dataset(path, mapping, True, id="copies", source="upload")


def test_gaps_block_new_admission_but_sensor_missing_values_and_later_start_pass(tmp_path):
    data = histories([100] * 25)
    frame = data.frame.copy()
    frame = frame[frame.cycle >= 5].copy()
    frame.loc[frame.cycle == 25, "sensor"] = np.nan
    mapping = ColumnMapping(equipment_id="equipment_id", cycle_index="cycle", sensors=["sensor"], failure_cycle="failure_cycle")
    path = tmp_path / "data.csv"
    frame.to_csv(path, index=False)
    validated_dataset(path, mapping, True, id="continuous", source="upload")
    frame[frame.cycle != 26].to_csv(path, index=False)
    with pytest.raises(ValueError, match="consecutive operating cycles"):
        validated_dataset(path, mapping, True, id="gapped", source="upload")


@pytest.mark.parametrize("lives,config,error", [
    ([40, 40, 100], EXPERIMENT, "Fold 3.*negative class"),
    ([19, 19, 19], EXPERIMENT, "Fold 1.*no scorable"),
])
def test_training_folds_require_scorable_rows_and_both_classes(lives, config, error):
    data = histories(lives, config=config)
    with pytest.raises(ValueError, match=error):
        check_training_feasibility(data, folds(data))


def test_training_without_positive_labels_is_rejected():
    data = histories([100, 100, 100])
    frame = data.frame.copy()
    frame["rul"] = 999
    with pytest.raises(ValueError, match="positive class"):
        check_training_feasibility(replace(data, frame=frame), folds(data))


def test_empty_validation_fold_is_rejected_without_requiring_two_validation_classes():
    data = histories([100, 100, 19])
    with pytest.raises(ValueError, match="Fold 3 validation.*no scorable"):
        check_training_feasibility(data, folds(data))
    data = histories([100, 100, 40])
    check_training_feasibility(data, folds(data))


def test_reserved_labels_do_not_affect_training_preflight():
    data = histories([100, 100, 100, 10])
    assignment = SplitAssignment(development=["0", "1", "2"], holdout=["3"], folds=[["0"], ["1"], ["2"]], seed=0, config_fingerprint=data.config.fingerprint())
    check_training_feasibility(data, assignment)
    changed = data.frame.copy()
    changed.loc[changed.equipment_id == "3", "rul"] = 999
    check_training_feasibility(replace(data, frame=changed), assignment)


@pytest.mark.parametrize("lead,horizon,boundary,support", [(10, 30, 45, 200), (114, 130, 145, 200), (115, 130, 145, 200), (10, 30, 45, 40)])
def test_supported_augmentation_is_deterministic(lead, horizon, boundary, support):
    config = replace(EXPERIMENT, min_useful_lead=lead, horizon_cycles=horizon, transition_band_end=boundary)
    first = sample_augmentation_faults(["sensor"], 45, 100, config, support=support)
    assert first == sample_augmentation_faults(["sensor"], 45, 100, config, support=support)
    assert all(lead + 5 <= fault.onset_before_failure <= support for fault in first)
    assert all(fault.onset_before_failure < max(120, horizon + 1, lead + 6) for fault in first)


def test_short_augmentation_support_fails_before_fitting_and_constant_sensor_skips():
    config = replace(EXPERIMENT, min_useful_lead=115, horizon_cycles=130, transition_band_end=145)
    data = histories([200, 200, 119], config=config)
    with pytest.raises(ValueError, match="Fold 1.*augmentation.*longer"):
        check_training_feasibility(data, folds(data))
    # Lower feature warm-up makes both classes available while support stays short.
    config = replace(config, feature_window=2)
    data = histories([200, 200, 119], config=config, constant=True)
    check_training_feasibility(data, folds(data))


def test_default_sampler_preserves_supported_original_interval():
    faults = sample_augmentation_faults(["sensor"], 1, 500, EXPERIMENT, support=200)
    assert min(f.onset_before_failure for f in faults) == 15
    assert max(f.onset_before_failure for f in faults) == 119


def fault_protocol(**changes):
    onset = changes.pop("onset", max(20, changes.get("min_useful_lead", 10)))
    return ExperimentProtocol(base_seed=0, scenarios=[FaultScenario(fault=FaultSpec(sensor="sensor", kind="dropout", duration="persistent", onset_before_failure=onset))], **changes)


def upload_and_confirm(client, data):
    frame = data.frame.rename(columns={"equipment_id": "id", "cycle": "step", "failure_cycle": "failure"})[["id", "step", "sensor", "failure"]]
    response = client.post("/api/datasets/upload", content=frame.to_csv(index=False), headers={"x-filename": "admission.csv"})
    assert response.status_code == 200, response.text
    dataset_id = response.json()["dataset_id"]
    confirmation = client.post(f"/api/datasets/{dataset_id}/confirm", json={"mapping": MAPPING.model_dump(mode="json"), "complete_histories": True})
    assert confirmation.status_code == 200, confirmation.text
    return dataset_id


def test_audit_single_class_fixture_fails_before_reservation_or_worker(local_settings, monkeypatch):
    from app.experiments.jobs import Jobs
    from app.main import create_app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(Jobs, "_run", lambda *args: pytest.fail("Rejected data launched a worker"))
    app = create_app()
    with TestClient(app) as client:
        dataset_id = upload_and_confirm(client, histories([100] + [40] * 25))
        workspace = app.state.jobs.workspace
        with workspace.connect() as conn:
            before = conn.execute("SELECT COUNT(*) FROM exposures").fetchone()[0]
        response = client.post("/api/experiments", json={"dataset_id": dataset_id, "protocol": fault_protocol().model_dump(mode="json")})
        assert response.status_code == 409, response.text
        assert "Fold" in response.json()["detail"] and "negative class" in response.json()["detail"]
        assert workspace.list() == []
        assert app.state.jobs.thread is None
        assert list((workspace.root / "experiments").glob("*")) == []
        with workspace.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM exposures").fetchone()[0] == before


@pytest.mark.parametrize("issue", ["copies", "gaps"])
def test_old_confirmed_upload_is_rechecked_before_new_run(local_settings, issue):
    from app.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    with TestClient(app) as client:
        dataset_id = upload_and_confirm(client, histories([100] * 25))
        workspace = app.state.jobs.workspace
        path = workspace.directory("datasets", dataset_id) / "data.csv"
        frame = pd.read_csv(path)
        if issue == "copies":
            frame["sensor"] = frame["step"].astype(float)
        else:
            frame = frame[frame.step != 22]
        frame.to_csv(path, index=False)
        response = client.post("/api/experiments", json={"dataset_id": dataset_id})
        assert response.status_code == 409, response.text
        assert ("Repeated readings" if issue == "copies" else "consecutive operating cycles") in response.json()["detail"]
        assert workspace.list() == []
        assert app.state.jobs.thread is None


def test_worker_rechecks_feasibility_before_development_exposure(local_settings, monkeypatch):
    from app.experiments.datasets import read_csv
    from app.experiments.provenance import source_digest
    from app.experiments import worker
    from app.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    with TestClient(app) as client:
        dataset_id = upload_and_confirm(client, histories([100] + [40] * 25))
        workspace = app.state.jobs.workspace
        config = protocol_config(fault_protocol())
        prepared = build_dataset(read_csv(workspace.directory("datasets", dataset_id) / "data.csv", "id"), MAPPING,
                                 dataset_id=dataset_id, source="upload", config=config)
        job_id = str(uuid4())
        workspace.reserve({"experiment_id": job_id, "dataset_id": dataset_id, "created_at": 1, "status": "queued",
                           "config": config.as_dict(), "source": "upload", "source_digest": source_digest(), "data_hash": prepared.data_hash})
        directory = workspace.directory("experiments", job_id)
        directory.mkdir(parents=True)
        class NoThread:
            def __init__(self, **kwargs):
                pass

            def start(self):
                pass

        with monkeypatch.context() as local:
            local.setattr(worker.threading, "Thread", NoThread)
            with pytest.raises(ValueError, match="negative class"):
                worker.run(workspace.root, job_id)
        assert "negative class" in (directory / "error.txt").read_text()
        from app.experiments.exposure import history_ids
        assert workspace.exposed(history_ids(prepared, prepared.equipment_ids).values()) == []


def test_valid_long_protocol_admission_uses_supported_bounds_without_starting_training(local_settings, monkeypatch):
    from app.experiments.jobs import Jobs
    from app.main import create_app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(Jobs, "_run", lambda *args: None)
    app = create_app()
    with TestClient(app) as client:
        dataset_id = upload_and_confirm(client, histories([300] * 25))
        protocol = fault_protocol(min_useful_lead=115, horizon_cycles=130, transition_band_end=145, onset=150)
        response = client.post("/api/experiments", json={"dataset_id": dataset_id, "protocol": protocol.model_dump(mode="json")})
        assert response.status_code == 201, response.text
        assert response.json()["config"]["min_useful_lead"] == 115


def test_legacy_gaps_and_copies_remain_visible_to_exposure_seeding(local_settings, monkeypatch):
    import json
    from app.config import reset_settings
    from app.experiments.datasets import register
    from app.experiments.exposure import history_ids, seed_known_exposure
    from app.experiments.store import Workspace

    monkeypatch.setenv("SIDEKICK_BUNDLE_PATH", str(local_settings / "no-benchmark.json"))
    reset_settings()
    workspace = Workspace(local_settings / "legacy")
    dataset_id, experiment_id = str(uuid4()), str(uuid4())
    dataset_dir = workspace.directory("datasets", dataset_id)
    dataset_dir.mkdir(parents=True)
    data = histories([100, 100])
    frame = data.frame.copy()
    frame["sensor"] = frame["cycle"].astype(float)
    frame = frame[frame.cycle != 22]
    mapping = ColumnMapping(equipment_id="equipment_id", cycle_index="cycle", sensors=["sensor"], failure_cycle="failure_cycle")
    frame[["equipment_id", "cycle", "sensor", "failure_cycle"]].to_csv(dataset_dir / "data.csv", index=False)
    registration = register(workspace, dataset_dir / "data.csv", dataset_id, "Legacy upload")
    registration.mapping = mapping
    registration.complete_histories = True
    workspace.save_dataset(registration.model_dump(mode="json"))
    record = ExperimentRecord(experiment_id=experiment_id, dataset_id=dataset_id, name="Legacy run", source="upload",
                              status="completed", created_at=1, finished_at=2, config=EXPERIMENT.as_dict(),
                              config_fingerprint=EXPERIMENT.fingerprint(), data_hash=data.data_hash, source_digest="recorded-legacy-source")
    workspace.reserve(record.model_dump(mode="json"))
    experiment_dir = workspace.directory("experiments", experiment_id)
    experiment_dir.mkdir(parents=True)
    bundle_path = experiment_dir / "bundle.json"
    bundle_path.write_text(json.dumps({"splits": {"development": ["0", "1"], "holdout": []}}))
    before = bundle_path.read_bytes()
    seed_known_exposure(workspace)
    prepared = build_dataset(frame, mapping, dataset_id=dataset_id, source="upload")
    identities = history_ids(prepared, prepared.equipment_ids)
    assert workspace.exposed(identities.values()) == list(identities.values())
    assert bundle_path.read_bytes() == before
