import json
from types import SimpleNamespace

import numpy as np
from app.config import EXPERIMENT
from app.experiments.validation import validate
from app.schemas import CandidateKind, FaultScenario, FaultSpec, Partition, ScenarioResult
from app.scoring.metrics import aggregate, score_engine
from app.scoring.selection import default_criteria


def test_failed_selected_model_does_not_get_replaced_by_reference(tmp_path, monkeypatch):
    spec = FaultSpec(sensor="s", kind="dropout", duration="persistent", onset_before_failure=60)
    config = SimpleNamespace(fault_scenarios=[FaultScenario(fault=spec).model_dump(mode="json")])
    main = SimpleNamespace(kind=CandidateKind.xgboost, config_id="xgb1")
    age = SimpleNamespace(kind=CandidateKind.age_baseline, config_id="age1")
    models = {"xgboost/xgb1": (main, None), "age_baseline/age1": (age, None)}

    def scored(candidate, *args):
        scores = np.ones(100) if candidate.kind == CandidateKind.age_baseline else np.zeros(100)
        measured = aggregate([score_engine("one", scores, np.arange(1, 101), np.arange(100, 0, -1), .5)])
        if candidate.kind == CandidateKind.age_baseline:
            measured.early_alarm_burden = 0
        row = ScenarioResult(scenario_id=spec.scenario_id, candidate=candidate.kind, config_id=candidate.config_id,
            partition=Partition.holdout, threshold=.5, fault=spec, metrics=measured, required=True, coverage_complete=True)
        return measured, [row], {}, {spec.scenario_id: []}

    monkeypatch.setattr("app.experiments.validation.score_model", scored)
    workspace = SimpleNamespace(update=lambda *args, **kwargs: None)
    bundle = SimpleNamespace(splits=SimpleNamespace(holdout=["one"]), development_selection=SimpleNamespace(criteria=default_criteria(EXPERIMENT)))
    dataset = SimpleNamespace(subset=lambda ids: None)
    manifest = {"candidate": "xgboost/xgb1", "thresholds": {name: .5 for name in models}}
    validate(workspace, {"experiment_id": "test"}, bundle, dataset, config, models, manifest, tmp_path)
    result = json.loads((tmp_path / "validation.json").read_text())
    assert result["selection"]["outcome"] == "none_qualified"
    assert result["selection"]["recommended"] is None
    assert result["selection"]["ranked"][1]["qualifies"]
