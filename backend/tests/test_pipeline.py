"""End-to-end behaviour: configuration, determinism, training and the bundle."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from app.config import EXPERIMENT, ExperimentConfig
from app.evidence.store import EvidenceStore, compare_runs
from app.schemas import CandidateKind, SelectionOutcome
from app.utils.determinism import derive_seed, rng
from app.utils.jsonio import canonical_dumps, hash_obj


class TestConfig:
    def test_the_fingerprint_is_stable(self):
        assert ExperimentConfig().fingerprint() == ExperimentConfig().fingerprint()

    def test_changing_any_setting_changes_the_fingerprint(self):
        for field, value in [
            ("horizon_cycles", 45),
            ("feature_window", 30),
            ("min_useful_lead", 12),
            ("base_seed", 1),
        ]:
            assert replace(EXPERIMENT, **{field: value}).fingerprint() != EXPERIMENT.fingerprint()

    def test_an_inconsistent_configuration_is_refused(self):
        with pytest.raises(ValueError, match="late window"):
            replace(EXPERIMENT, late_window_end=25).validate()
        with pytest.raises(ValueError, match="transition band"):
            replace(EXPERIMENT, transition_band_end=20).validate()
        with pytest.raises(ValueError, match="inside the horizon"):
            replace(EXPERIMENT, min_useful_lead=40).validate()

    def test_a_fault_onset_inside_the_useful_window_is_refused(self):
        with pytest.raises(ValueError, match="cannot be scored"):
            replace(EXPERIMENT, fault_onsets=(5,)).validate()

    def test_the_shipped_configuration_is_valid(self):
        EXPERIMENT.validate()


class TestDeterminism:
    def test_the_same_label_path_gives_the_same_seed(self):
        assert derive_seed(7, "folds", 2) == derive_seed(7, "folds", 2)

    def test_different_label_paths_give_different_seeds(self):
        assert derive_seed(7, "folds") != derive_seed(7, "faults")
        assert derive_seed(7, "a", "b") != derive_seed(7, "ab")

    def test_generators_are_reproducible(self):
        assert rng(1, "x").normal(size=5).tolist() == rng(1, "x").normal(size=5).tolist()

    def test_canonical_encoding_ignores_key_order(self):
        assert canonical_dumps({"a": 1, "b": 2}) == canonical_dumps({"b": 2, "a": 1})

    def test_hashing_handles_numpy_values(self):
        assert hash_obj({"x": np.float64(1.5)}) == hash_obj({"x": 1.5})


class TestTraining:
    def test_out_of_fold_predictions_cover_every_development_engine(self, evaluation):
        development = set(evaluation.training.splits.development)
        for candidate_name, per_engine in evaluation.training.out_of_fold.items():
            assert set(per_engine) == development, candidate_name

    def test_a_validation_engine_is_never_in_its_own_fold_training_set(self, evaluation):
        for fold in evaluation.training.folds:
            assert not set(fold.train_engines) & set(fold.validation_engines)

    def test_the_holdout_is_absent_from_every_fold(self, evaluation):
        holdout = set(evaluation.training.splits.holdout)
        for fold in evaluation.training.folds:
            assert not holdout & set(fold.train_engines)
            assert not holdout & set(fold.validation_engines)

    def test_each_fold_fits_its_own_preprocessing(self, evaluation):
        medians = [tuple(fold.preprocessor.medians.round(9)) for fold in evaluation.training.folds]
        assert len(set(medians)) > 1, "identical medians suggest preprocessing is shared"

    def test_all_four_families_are_present(self, evaluation):
        kinds = {candidate.kind for candidate in evaluation.training.specs.values()}
        assert kinds == set(CandidateKind)

    def test_the_age_baseline_sees_no_sensor_feature(self, evaluation):
        baseline = next(
            c for c in evaluation.training.specs.values() if c.kind == CandidateKind.age_baseline
        )
        assert baseline.uses_sensors is False

    def test_the_augmented_variant_refuses_to_train_without_corrupted_rows(self, evaluation):
        from app.models.candidates import AugmentedXGBoostCandidate
        from app.models.design import build_design

        fold = evaluation.training.folds[0]
        design = build_design(
            evaluation.training.dataset, fold.builder, equipment_ids=fold.train_engines
        )
        with pytest.raises(ValueError, match="requires augmented training rows"):
            AugmentedXGBoostCandidate("aug1", {}).fit(design, augmented=None)


class TestFaultInvariance:
    def test_the_age_baseline_is_unaffected_by_every_sensor_fault(self, evaluation):
        """It reads no sensor, so this must hold exactly, not approximately."""
        name = next(
            n
            for n, c in evaluation.training.specs.items()
            if c.kind == CandidateKind.age_baseline
        )
        clean = evaluation.clean[name].detection_fraction
        under_fault = {
            round(m.detection_fraction, 12)
            for m in evaluation.matrix.for_candidate(name).values()
        }
        assert under_fault == {round(clean, 12)}

    def test_corrupting_a_sensor_changes_what_a_sensor_model_predicts(self, evaluation):
        """Checked on the scores themselves.

        An aggregate detection rate can stay pinned at 100% on easy data while the
        underlying scores move a great deal, so asserting on the rate would let a
        broken injection path pass unnoticed.
        """
        from app.faults.inject import apply_fault
        from app.models.design import EngineBlock, design_from_blocks
        from app.schemas import FaultDuration, FaultKind, FaultSpec

        fold = evaluation.training.folds[0]
        equipment_id = fold.validation_engines[0]
        block = fold.blocks[equipment_id]
        builder = fold.builder
        sensor = next(s for s in builder.sensors if builder.preprocessor.std_of(s) > 0)

        clean_design = design_from_blocks(
            {equipment_id: block}, builder.feature_names(), equipment_ids=[equipment_id]
        )
        injected = apply_fault(
            evaluation.training.dataset.sensor_matrix(equipment_id)[
                :, builder.preprocessor.index_of(sensor)
            ],
            block.rul,
            FaultSpec(
                kind=FaultKind.stuck,
                duration=FaultDuration.persistent,
                sensor=sensor,
                onset_before_failure=max(evaluation.training.config.fault_onsets),
            ),
            sensor_std=builder.preprocessor.std_of(sensor),
            config=evaluation.training.config,
        )
        assert injected.applied

        features = block.features.copy()
        builder.rebuild_sensor(features, injected.values, sensor)
        faulted_design = design_from_blocks(
            {
                equipment_id: EngineBlock(
                    equipment_id=equipment_id,
                    features=features,
                    labels=block.labels,
                    cycles=block.cycles,
                    rul=block.rul,
                    rows=block.rows,
                    scorable=block.scorable,
                )
            },
            builder.feature_names(),
            equipment_ids=[equipment_id],
        )

        for name, candidate in fold.candidates.items():
            clean_scores = candidate.score(clean_design)
            faulted_scores = candidate.score(faulted_design)
            if evaluation.training.specs[name].kind == CandidateKind.age_baseline:
                assert np.array_equal(clean_scores, faulted_scores), (
                    "the age baseline reads no sensor and must be unchanged"
                )
            else:
                assert not np.allclose(clean_scores, faulted_scores), (
                    f"{name} ignored a corrupted sensor entirely, so the injection "
                    "path is not reaching the model"
                )


class TestPipelineResult:
    def test_every_candidate_gets_a_threshold_and_a_verdict(self, evaluation):
        assert set(evaluation.thresholds) == set(evaluation.training.specs)
        assert len(evaluation.selection.ranked) == len(evaluation.training.specs)

    def test_the_outcome_is_one_of_the_two_permitted_values(self, evaluation):
        assert evaluation.selection.outcome in set(SelectionOutcome)

    def test_a_recommendation_only_appears_when_something_qualified(self, evaluation):
        if evaluation.selection.outcome == SelectionOutcome.none_qualified:
            assert evaluation.selection.recommended is None
        else:
            assert evaluation.selection.recommended.qualifies

    def test_required_scenarios_are_marked_as_such(self, evaluation):
        required = {r.scenario_id for r in evaluation.scenario_results if r.required}
        assert required == evaluation.required_scenario_ids

    def test_clean_results_are_present_for_every_candidate(self, evaluation):
        clean = [r for r in evaluation.scenario_results if r.scenario_id == "clean"]
        assert len(clean) == len(evaluation.training.specs)


class TestBundle:
    def test_the_bundle_round_trips_through_json(self, bundle, tmp_path):
        from app.evidence.bundle import load_bundle, write_bundle

        path = write_bundle(bundle, tmp_path / "bundle.json")
        reloaded = load_bundle(path)
        assert reloaded.config_fingerprint == bundle.config_fingerprint
        assert len(reloaded.scenario_results) == len(bundle.scenario_results)

    def test_the_bundle_states_its_limitations(self, bundle):
        assert len(bundle.limitations) >= 5

    def test_the_bundle_records_the_partitions_it_used(self, bundle):
        assert bundle.splits.holdout
        assert bundle.splits.development
        assert bundle.splits.seed

    def test_replay_series_alert_flags_agree_with_the_threshold_rule(self, bundle):
        for series in bundle.replay_series:
            if not series.episodes:
                continue
            covered = set()
            for episode in series.episodes:
                covered |= set(range(episode.start_cycle, episode.end_cycle + 1))
            flagged = {point.cycle for point in series.points if point.alert}
            assert flagged == covered

    def test_a_faulted_series_carries_both_readings(self, bundle):
        faulted = [s for s in bundle.replay_series if s.fault is not None]
        if not faulted:
            pytest.skip("no faulted replay series in this bundle")
        for series in faulted:
            pairs = [(p.sensor_clean, p.sensor_faulted) for p in series.points]
            assert any(clean is not None for clean, _ in pairs)
            assert any(clean != altered for clean, altered in pairs)


class TestEvidenceStore:
    def test_a_run_record_captures_provenance(self, tmp_path):
        store = EvidenceStore(tmp_path)
        record = store.start_run("training", data_hash="abc123", params={"x": 1})
        assert record.config_fingerprint == EXPERIMENT.fingerprint()
        assert record.data_hash == "abc123"
        assert record.seed == EXPERIMENT.base_seed
        assert store.get(record.run_id).run_id == record.run_id

    def test_metrics_are_appended(self, tmp_path):
        store = EvidenceStore(tmp_path)
        record = store.start_run("selection")
        store.log_metrics(record, {"detection": 0.9})
        assert store.get(record.run_id).metrics["detection"] == pytest.approx(0.9)

    def test_runs_are_listed_newest_first_and_filterable(self, tmp_path):
        store = EvidenceStore(tmp_path)
        store.start_run("training")
        store.start_run("selection")
        assert len(store.list_runs()) == 2
        assert len(store.list_runs(kind="selection")) == 1

    def test_identical_metrics_count_as_reproduced(self, tmp_path):
        store = EvidenceStore(tmp_path)
        first = store.start_run("final_evaluation")
        store.log_metrics(first, {"detection": 0.85})
        second = store.start_run("final_evaluation")
        store.log_metrics(second, {"detection": 0.85})
        assert compare_runs(first, second).reproduced

    def test_a_changed_metric_fails_the_check(self, tmp_path):
        store = EvidenceStore(tmp_path)
        first = store.start_run("final_evaluation")
        store.log_metrics(first, {"detection": 0.85})
        second = store.start_run("final_evaluation")
        store.log_metrics(second, {"detection": 0.86})
        check = compare_runs(first, second)
        assert not check.reproduced
        assert check.max_absolute_difference == pytest.approx(0.01)

    def test_two_runs_sharing_no_metrics_do_not_count_as_reproduced(self, tmp_path):
        store = EvidenceStore(tmp_path)
        first = store.start_run("final_evaluation")
        store.log_metrics(first, {"a": 1.0})
        second = store.start_run("final_evaluation")
        store.log_metrics(second, {"b": 1.0})
        assert not compare_runs(first, second).reproduced
