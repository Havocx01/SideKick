"""Compound measurement faults and fixed grouped-development evaluation."""
from dataclasses import replace
import json
import os

import numpy as np
import pandas as pd
import pytest

from app.config import EXPERIMENT
from app.data.synthetic import make_synthetic_dataset
from app.faults.inject import apply_fault
from app.faults.runner import run_matrix
from app.features.build import FeatureBuilder, Preprocessor
from app.models.candidates import AgeBaselineCandidate, LogisticRegressionCandidate
from app.models.train import train_development
from app.schemas import FaultSpec


def component(sensor="temp_bearing", **changes):
    return {"sensor": sensor, "kind": "dropout", "duration": "persistent", "onset_before_failure": 40, **changes}


def scenario(*components):
    from app.faults.scenarios import FaultCase
    return FaultCase(components=list(components) or [component(), component("vibration_rms", kind="drift", severity_sd=1.5, sign=1, ramp_cycles=10)])


def policy(**changes):
    from app.faults.scenarios import FaultPolicy
    return FaultPolicy(allowed_sensors=("temp_bearing", "vibration_rms"), **changes)


@pytest.fixture(scope="module")
def fitted():
    config = replace(EXPERIMENT, holdout_engines=4, n_folds=2, feature_window=5,
        horizon_cycles=20, min_useful_lead=5, late_window_end=4, transition_band_end=30, configs_per_candidate=1)
    dataset = make_synthetic_dataset(n_equipment=26, min_life=85, max_life=100, config=config)
    training = train_development(dataset, config=config,
        candidates=[LogisticRegressionCandidate("lr-probe", {"max_iter": 300}), AgeBaselineCandidate("age-probe")])
    return training


def evaluator(fitted, **policy_changes):
    from app.faults.evaluator import FixedDevelopmentEvaluator
    return FixedDevelopmentEvaluator(fitted, {"logistic_regression/lr-probe": .5, "age_baseline/age-probe": 60.0}, policy(**policy_changes))


def test_compound_identity_is_order_independent_and_legacy_identity_is_unchanged():
    first = scenario()
    assert first.scenario_id == scenario(*reversed(first.model_dump(mode="json")["components"])).scenario_id
    one = scenario(component())
    assert one.scenario_id.startswith("single-v1-")
    assert FaultSpec(**component()).scenario_id == "dropout-persistent-temp_bearing-on40"
    changed = scenario(component(), component("vibration_rms", kind="stuck", onset_before_failure=30))
    assert changed.scenario_id != first.scenario_id
    with pytest.raises(ValueError):
        first.components[0].sensor = "other"


def test_close_float_severities_do_not_alias_in_new_scenario_ids():
    first = scenario(component(kind="drift", severity_sd=1.0000001, sign=1, ramp_cycles=10))
    second = scenario(component(kind="drift", severity_sd=1.0000002, sign=1, ramp_cycles=10))
    assert first.scenario_id != second.scenario_id


@pytest.mark.parametrize("parts", [[], [component(), component()], [component(sensor="")],
    [component(kind="drift", severity_sd=float("nan"), sign=1, ramp_cycles=10)],
    [component(duration="transient", length=0)], [component(onset_before_failure=True)],
    [component(onset_before_failure=None)], [component(kind="drift", severity_sd=1.0, sign=0, ramp_cycles=10)],
    [component(length=5)], [component(kind="drift", severity_sd=-1.0, sign=1, ramp_cycles=10)]])
def test_invalid_or_ambiguous_components_are_rejected(parts):
    from app.faults.scenarios import FaultCase
    with pytest.raises(ValueError):
        FaultCase(components=parts)


def test_policy_checks_sensor_budget_combinations_and_documented_bounds():
    p = policy(max_components=1)
    with pytest.raises(ValueError, match="budget"):
        p.check(scenario(), EXPERIMENT)
    with pytest.raises(ValueError, match="allowed"):
        policy().check(scenario(component("unknown")), EXPERIMENT)
    with pytest.raises(ValueError, match="severity"):
        policy().check(scenario(component(kind="drift", severity_sd=4.0, sign=1, ramp_cycles=10)), EXPERIMENT)
    with pytest.raises(ValueError, match="group"):
        policy(allowed_groups=(("temp_bearing",), ("vibration_rms",))).check(scenario(), EXPERIMENT)
    assert "not equipment-validated" in policy().assumptions


def test_atomic_injection_rebuilds_the_same_features_as_manual_independent_columns(fitted):
    from app.faults.scenarios import apply_case
    fold = fitted.folds[0]
    equipment = fold.validation_engines[0]
    raw = fitted.dataset.sensor_matrix(equipment)
    before = raw.copy()
    rul = fold.blocks[equipment].rul
    case = scenario()
    result = apply_case(raw, rul, case, fold.builder, fitted.config)
    assert result.applied and len(result.components) == 2
    manual = raw.copy()
    for atom in case.components:
        index = fold.preprocessor.index_of(atom.sensor)
        injected = apply_fault(raw[:, index], rul, atom, sensor_std=fold.preprocessor.std_of(atom.sensor), config=fitted.config)
        manual[:, index] = injected.values
    np.testing.assert_array_equal(result.values, manual)
    np.testing.assert_array_equal(raw, before)
    np.testing.assert_array_equal(fold.builder.build_engine(result.values), fold.builder.build_engine(manual))
    unavailable = apply_case(raw, rul, scenario(component(), component("vibration_rms", onset_before_failure=10000)), fold.builder, fitted.config)
    assert not unavailable.applied and unavailable.values is None and unavailable.reasons


def test_explicit_zero_seed_is_reproducible_and_distinct_from_default_seed(fitted):
    from app.faults.scenarios import apply_case
    fold = fitted.folds[0]
    equipment = fold.validation_engines[0]
    raw = fitted.dataset.sensor_matrix(equipment)
    rul = fold.blocks[equipment].rul
    case = scenario(component(onset_before_failure=None, seed=0))
    first = apply_case(raw, rul, case, fold.builder, fitted.config)
    second = apply_case(raw, rul, case, fold.builder, replace(fitted.config, base_seed=999))
    assert first.applied and second.applied
    np.testing.assert_array_equal(first.values, second.values)


def test_fixed_evaluation_matches_legacy_single_fault_and_never_fits(fitted, monkeypatch):
    fixed = evaluator(fitted)
    monkeypatch.setattr(LogisticRegressionCandidate, "fit", lambda *_a, **_k: pytest.fail("Evaluation retrained a model"))
    case = scenario(component())
    legacy = run_matrix(fitted, [FaultSpec(**component())], fixed.thresholds, config=fitted.config)
    before = fitted.dataset.frame.copy(deep=True)
    result = fixed.evaluate(case)
    assert result.status == "complete" and result.expected_histories == len(fitted.splits.development)
    assert result.evaluated_histories == result.expected_histories
    for model in result.models:
        assert model.faulted.model_dump() == legacy.metrics[model.candidate, FaultSpec(**component()).scenario_id].model_dump()
        assert model.clean_matched.engines == model.faulted.engines
        assert len(model.pairs) == result.expected_histories
    assert fixed.evaluate(case).model_dump() == result.model_dump()
    assert fitted.dataset.frame.equals(before)


def test_compound_scores_are_reproducible_and_return_defensive_copies(fitted):
    fixed = evaluator(fitted)
    first = fixed.evaluate(scenario())
    second = evaluator(fitted).evaluate(scenario())
    assert first.model_dump() == second.model_dump()
    assert first.partition == "out_of_fold" and first.policy_fingerprint and first.context_fingerprint
    first.models[0].pairs.clear()
    assert fixed.evaluate(scenario()).models[0].pairs
    age = next(model for model in second.models if model.candidate.startswith("age_baseline"))
    assert age.detection_delta == 0 and age.alarm_burden_delta == 0
    assert all(pair.clean_prediction_digest == pair.faulted_prediction_digest for pair in age.pairs)


def test_partial_coverage_uses_matched_clean_population_and_empty_is_unavailable(fitted):
    fixed = evaluator(fitted, max_onset=200)
    result = fixed.evaluate(scenario(component(onset_before_failure=90)))
    assert result.status == "partial" and 0 < result.evaluated_histories < result.expected_histories
    assert len(result.exclusions) == result.expected_histories - result.evaluated_histories
    for model in result.models:
        assert model.clean_matched.engines == model.faulted.engines == result.evaluated_histories
        assert model.clean_all.engines == result.expected_histories
    empty = fixed.evaluate(scenario(component(onset_before_failure=150)))
    assert empty.status == "not_applicable" and empty.evaluated_histories == 0
    assert all(m.faulted is None and m.clean_matched is None and m.detection_delta is None for m in empty.models)


def test_constant_stuck_or_already_missing_readings_are_not_counted_as_applied(fitted):
    from app.faults.scenarios import apply_case
    raw = np.full((60, 1), 7.0)
    preprocessor = Preprocessor(("temp_bearing",), np.array([7.]), np.array([1.]))
    builder = FeatureBuilder(preprocessor, fitted.config)
    result = apply_case(raw, np.arange(59, -1, -1), scenario(component(kind="stuck")), builder, fitted.config)
    assert not result.applied and result.values is None
    result = apply_case(raw * np.nan, np.arange(59, -1, -1), scenario(component()), builder, fitted.config)
    assert not result.applied and result.values is None


def test_reserved_and_overlapping_training_contexts_are_rejected_before_scoring(fitted):
    from app.faults.evaluator import FixedDevelopmentEvaluator
    from copy import deepcopy
    contaminated = deepcopy(fitted)
    contaminated.splits.holdout.append(contaminated.splits.development[0])
    with pytest.raises(ValueError, match="holdout|reserved"):
        evaluator(contaminated)
    contaminated = deepcopy(fitted)
    contaminated.folds[0].train_engines.append(contaminated.folds[0].validation_engines[0])
    with pytest.raises(ValueError, match="fold"):
        evaluator(contaminated)
    with pytest.raises(ValueError, match="threshold"):
        FixedDevelopmentEvaluator(fitted, {"logistic_regression/lr-probe": float("nan")}, policy())
    with pytest.raises(ValueError, match="limit"):
        evaluator(fitted, max_histories=1)


def test_budget_cancellation_and_input_snapshot(fitted):
    from app.faults.evaluator import EvaluationStopped
    fixed = evaluator(fitted, max_evaluations=1)
    with pytest.raises(EvaluationStopped):
        fixed.evaluate(scenario(), cancelled=lambda: True)
    first = fixed.evaluate(scenario())
    assert fixed.evaluate(scenario()).model_dump() == first.model_dump()
    with pytest.raises(EvaluationStopped, match="budget"):
        fixed.evaluate(scenario(component()))
    from copy import deepcopy
    source = deepcopy(fitted)
    snapshot = evaluator(source)
    source.dataset.frame.loc[:, "temp_bearing"] = 0
    assert snapshot.evaluate(scenario()).model_dump() == evaluator(fitted).evaluate(scenario()).model_dump()


def test_evaluator_never_requests_reserved_readings(fitted, monkeypatch):
    from app.data.dataset import Dataset
    seen = set()
    original = Dataset.sensor_matrix
    def readings(dataset, equipment):
        assert equipment not in fitted.splits.holdout
        seen.add(equipment)
        return original(dataset, equipment)
    monkeypatch.setattr(Dataset, "sensor_matrix", readings)
    assert evaluator(fitted).evaluate(scenario()).status == "complete"
    assert seen == set(fitted.splits.development)


def test_threshold_changes_are_returned_as_copies_and_never_retuned(fitted):
    fixed = evaluator(fitted)
    thresholds = fixed.thresholds
    thresholds["logistic_regression/lr-probe"] = 100
    result = fixed.evaluate(scenario())
    assert next(m.threshold for m in result.models if m.candidate == "logistic_regression/lr-probe") == .5
    for name, value in (("policy", policy(max_evaluations=2)), ("config", EXPERIMENT), ("context_fingerprint", "edited")):
        with pytest.raises(AttributeError):
            setattr(fixed, name, value)


def test_bad_scores_raise_instead_of_becoming_model_failures(fitted, monkeypatch):
    fixed = evaluator(fitted, max_evaluations=1)
    monkeypatch.setattr(LogisticRegressionCandidate, "score", lambda _self, design: np.full(len(design), np.nan))
    with pytest.raises(ValueError, match="prediction"):
        fixed.evaluate(scenario())
    from app.faults.evaluator import EvaluationStopped
    with pytest.raises(EvaluationStopped, match="budget"):
        fixed.evaluate(scenario())


def test_cooperative_timeout_and_mid_run_cancellation_leave_no_partial_result(fitted, monkeypatch):
    from app.faults.evaluator import EvaluationStopped
    fixed = evaluator(fitted)
    with monkeypatch.context() as scoped:
        ticks = iter([0.0, 31.0])
        scoped.setattr("app.faults.evaluator.time.monotonic", lambda: next(ticks))
        with pytest.raises(EvaluationStopped, match="time limit"):
            fixed.evaluate(scenario())
    checks = 0
    def cancel():
        nonlocal checks
        checks += 1
        return checks > 4
    with pytest.raises(EvaluationStopped):
        fixed.evaluate(scenario(), cancelled=cancel)
    assert fixed.evaluate(scenario()).status == "complete"


@pytest.mark.parametrize("filename", ["scenario.json", "evaluation.json"])
def test_replay_rejects_tampered_json_before_deserialization(fitted, tmp_path, monkeypatch, filename):
    from app.faults.replay import export_evaluation, replay_evaluation
    fixed = evaluator(fitted)
    directory = tmp_path / "replay"
    export_evaluation(fixed, fixed.evaluate(scenario()), directory)
    with (directory / filename).open("a") as stream:
        stream.write(" ")
    monkeypatch.setattr("app.faults.replay.joblib.load", lambda *_a, **_k: pytest.fail("Loaded unchecked artifact"))
    with pytest.raises(ValueError, match="checksum"):
        replay_evaluation(directory, trusted=True)


def test_export_rejects_edited_evidence(fitted, tmp_path):
    from app.faults.replay import export_evaluation
    fixed = evaluator(fitted)
    report = fixed.evaluate(scenario())
    report.models[0].faulted.detected += 1
    with pytest.raises(ValueError, match="recorded engine result"):
        export_evaluation(fixed, report, tmp_path / "edited")
    assert not (tmp_path / "edited").exists()


def test_returned_nested_outcomes_cannot_poison_another_scenario(fitted):
    fixed = evaluator(fitted)
    first = fixed.evaluate(scenario())
    age = next(model for model in first.models if model.candidate.startswith("age_baseline"))
    age.pairs[0].clean.detected = not age.pairs[0].clean.detected
    second = fixed.evaluate(scenario(component(onset_before_failure=30)))
    age_after = next(model for model in second.models if model.candidate.startswith("age_baseline"))
    assert age_after.clean_all.detected == age.clean_all.detected
    assert age_after.detection_delta == 0


@pytest.mark.parametrize("change", ["append", "rename"])
def test_actual_frame_membership_overrides_stale_dataset_caches(fitted, change):
    from copy import deepcopy
    source = deepcopy(fitted)
    assert source.dataset.equipment_ids
    source.dataset.rows_for(source.splits.development[0])
    reserved = source.splits.holdout[0]
    if change == "append":
        row = source.dataset.frame.iloc[[0]].copy()
        row["equipment_id"] = reserved
        source.dataset.frame = pd.concat([source.dataset.frame, row], ignore_index=True)
    else:
        source.dataset.frame.loc[source.dataset.frame.equipment_id == source.splits.development[0], "equipment_id"] = reserved
    with pytest.raises(ValueError, match="reserved|development-only"):
        evaluator(source)


def test_context_fingerprint_ignores_platform_newlines(fitted, monkeypatch):
    monkeypatch.setattr(os, "linesep", "\n")
    linux = evaluator(fitted)
    monkeypatch.setattr(os, "linesep", "\r\n")
    windows = evaluator(fitted)
    assert linux.context_fingerprint == windows.context_fingerprint
    assert linux.evaluate(scenario()) == windows.evaluate(scenario())


def test_snapshot_rebuilds_row_caches_and_discards_unused_training_blocks(fitted):
    from copy import deepcopy
    source = deepcopy(fitted)
    source.dataset.rows_for(source.splits.development[0])
    source.dataset.frame = source.dataset.frame.sort_values(["equipment_id", "cycle"], ascending=[False, True]).reset_index(drop=True)
    fixed = evaluator(source)
    result = fixed.evaluate(scenario())
    expected = evaluator(fitted).evaluate(scenario())
    assert [m.model_dump() for m in result.models] == [m.model_dump() for m in expected.models]
    assert all(not fold.blocks for fold in fixed._training.folds)
    assert not fixed._training.out_of_fold


@pytest.mark.parametrize("change", ["window", "sensor_order"])
def test_effective_feature_pipeline_must_match_its_declared_configuration(fitted, change):
    from copy import deepcopy
    source = deepcopy(fitted)
    for fold in source.folds:
        if change == "window":
            fold.builder.window -= 1
        else:
            fold.builder.sensors.reverse()
    with pytest.raises(ValueError, match="preprocessing|feature"):
        evaluator(source)


def test_local_package_replay_requires_explicit_trust_and_checks_integrity(fitted, tmp_path, monkeypatch):
    from app.faults.replay import export_evaluation, replay_evaluation
    fixed = evaluator(fitted)
    result = fixed.evaluate(scenario())
    directory = tmp_path / "replay"
    export_evaluation(fixed, result, directory)
    with pytest.raises(ValueError, match="trust"):
        replay_evaluation(directory)
    monkeypatch.setattr(LogisticRegressionCandidate, "fit", lambda *_a, **_k: pytest.fail("Replay retrained a model"))
    replayed = replay_evaluation(directory, trusted=True)
    assert replayed.model_dump() == result.model_dump()
    with pytest.raises(FileExistsError):
        export_evaluation(fixed, result, directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["context_fingerprint"] == result.context_fingerprint
    with (directory / "context.joblib").open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        replay_evaluation(directory, trusted=True)
