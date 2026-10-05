from dataclasses import replace

import numpy as np
import pytest
from app.config import EXPERIMENT
from app.data.contract import build_dataset
from app.data.synthetic import make_synthetic_dataset
from app.experiments.exposure import history_ids
from app.experiments.protocol import protocol_config
from app.models.splits import fold_pairs, make_splits
from app.models.thresholds import choose_threshold
from app.schemas import ExperimentProtocol, FaultScenario, FaultSpec
from app.scoring.metrics import aggregate, score_engine
from app.scoring.selection import build_verdict, default_criteria


def test_protocol_windows_and_required_cases():
    with pytest.raises(ValueError):
        ExperimentProtocol(min_useful_lead=40, horizon_cycles=30)
    with pytest.raises(ValueError):
        ExperimentProtocol(scenarios=[FaultScenario(fault=FaultSpec(sensor="s", kind="dropout", duration="persistent", onset_before_failure=60), required=False)])
    with pytest.raises(ValueError):
        ExperimentProtocol(scenarios=[FaultScenario(fault=FaultSpec(sensor="s", kind="drift", duration="persistent", onset_before_failure=60, severity_sd=float("nan"), sign=1, ramp_cycles=20))])


def test_protocol_fingerprint_tracks_criteria_and_faults():
    protocol = ExperimentProtocol(scenarios=[FaultScenario(fault=FaultSpec(sensor="s", kind="dropout", duration="persistent", onset_before_failure=60))])
    initial = protocol_config(protocol).fingerprint()
    assert initial != protocol_config(protocol.model_copy(update={"min_detection_fraction": .8})).fingerprint()
    changed = protocol.model_copy(update={"scenarios": [FaultScenario(fault=protocol.scenarios[0].fault.model_copy(update={"onset_before_failure": 30}))]})
    assert initial != protocol_config(changed).fingerprint()


def test_no_early_life_cycles_is_unavailable_and_cannot_pass():
    scoring = score_engine("one", np.ones(20), np.arange(1, 21), np.arange(20, 0, -1), .5)
    metrics = aggregate([scoring])
    assert metrics.early_alarm_burden is None
    choice = choose_threshold(np.ones(20), lambda threshold: metrics, default_criteria())
    assert not choice.within_budget
    verdict = build_verdict(candidate="age_baseline", config_id="age1", threshold=.5, clean=metrics, required=[], criteria=default_criteria())
    assert not verdict.qualifies
    assert aggregate([]).early_alarm_burden is None


def test_history_identity_ignores_labels_names_and_channel_order():
    dataset = make_synthetic_dataset(n_equipment=25, min_life=100, max_life=110)
    equipment = dataset.equipment_ids[0]
    original = history_ids(dataset, [equipment])[equipment]
    changed_frame = dataset.frame.copy()
    changed_frame["failure_cycle"] += 1
    changed_frame["rul"] += 1
    changed = replace(dataset, frame=changed_frame)
    assert history_ids(changed, [equipment])[equipment] == original
    renamed = changed_frame.copy()
    renamed.loc[renamed.equipment_id == equipment, "equipment_id"] = "renamed"
    assert history_ids(replace(dataset, frame=renamed), ["renamed"])["renamed"] == original
    assert history_ids(replace(dataset, mapping=dataset.mapping.model_copy(update={"sensors": list(reversed(dataset.sensors))})), [equipment])[equipment] == original
    changed_frame = dataset.frame.copy()
    changed_frame.loc[0, dataset.sensors[0]] += 1
    assert history_ids(replace(dataset, frame=changed_frame), [equipment])[equipment] != original
    mapping = dataset.mapping.model_copy(update={"equipment_id": "equipment_id", "failure_cycle": "failure_cycle"})
    baseline = build_dataset(dataset.frame, mapping, dataset_id="baseline", source="test")
    rebuilt = build_dataset(changed.frame, mapping, dataset_id="changed", source="test")
    assert rebuilt.data_hash != baseline.data_hash


def test_equipment_partitions_are_separate():
    dataset = make_synthetic_dataset(n_equipment=30, min_life=100, max_life=110)
    splits = make_splits(dataset)
    for train, validation in fold_pairs(splits):
        assert not set(train) & set(validation)
        assert not set(train + validation) & set(splits.holdout)
    assert len(splits.holdout) == EXPERIMENT.holdout_engines
