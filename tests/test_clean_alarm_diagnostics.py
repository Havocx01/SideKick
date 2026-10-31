from dataclasses import replace
import importlib.util
from pathlib import Path

import numpy as np
import pytest

from app.config import EXPERIMENT
from app.data.synthetic import make_synthetic_dataset
from app.models.candidates import LogisticRegressionCandidate
from app.models.train import train_development
from app.schemas import SplitAssignment
from app.scoring.metrics import score_engine

spec = importlib.util.spec_from_file_location('alarmDiagnostics', Path(__file__).parents[1] / 'scripts/diagnose_clean_alarms.py')
diagnostics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostics)


@pytest.fixture
def development():
    config = replace(EXPERIMENT, holdout_engines=0, n_folds=3, feature_window=5, horizon_cycles=20,
        min_useful_lead=5, late_window_end=4, transition_band_end=30, configs_per_candidate=1)
    dataset = make_synthetic_dataset(n_equipment=9, min_life=70, max_life=80, config=config)
    frame = dataset.frame.copy()
    frame[dataset.sensors] = np.abs(frame[dataset.sensors]) + 1
    return replace(dataset, frame=frame)


def test_relative_rms_is_causal_scale_invariant_and_keeps_labels(development):
    normalized = diagnostics.relativeRms(development, 5)
    assert not np.shares_memory(normalized.frame.to_numpy(), development.frame.to_numpy())
    assert normalized.data_hash != development.data_hash
    np.testing.assert_array_equal(normalized.label_vector(), development.label_vector())
    readings = development.sensor_matrix(development.equipment_ids[0])
    first = np.log1p(readings[0] / readings[0])
    np.testing.assert_allclose(normalized.sensor_matrix(development.equipment_ids[0])[0], first)
    changed = development.frame.copy()
    changed.loc[changed.index[-1], development.sensors] *= 100
    after = diagnostics.relativeRms(replace(development, frame=changed), 5)
    np.testing.assert_allclose(normalized.frame[development.sensors].iloc[:-1], after.frame[development.sensors].iloc[:-1])
    scaled = development.frame.copy()
    scaled[development.sensors] *= 100
    np.testing.assert_allclose(diagnostics.relativeRms(replace(development, frame=scaled), 5).frame[development.sensors], normalized.frame[development.sensors])
    assert normalized.frame[['equipment_id', 'cycle', 'rul']].equals(development.frame[['equipment_id', 'cycle', 'rul']])


def test_relative_rms_rejects_invalid_clean_inputs_and_handles_zero_prefix(development):
    for value in (-1, np.nan, np.inf):
        frame = development.frame.copy()
        frame.loc[0, development.sensors[0]] = value
        with pytest.raises(ValueError, match='nonnegative finite'):
            diagnostics.relativeRms(replace(development, frame=frame), 5)
    with pytest.raises(ValueError, match='positive integer'):
        diagnostics.relativeRms(development, 0)
    frame = development.frame.copy()
    frame.loc[:4, development.sensors[0]] = 0
    normalized = diagnostics.relativeRms(replace(development, frame=frame), 5)
    assert np.isfinite(normalized.frame[development.sensors].to_numpy()).all()
    np.testing.assert_array_equal(normalized.frame.loc[:4, development.sensors[0]], 0)


def test_relative_reference_freezes_after_warmup_and_resets_for_each_history(development):
    frame = development.frame.copy()
    frame[development.sensors] = 2.
    first = development.equipment_ids[0]
    start, stop = development.rows_for(first)
    frame.loc[start+5:stop-1, development.sensors] = 20.
    normalized = diagnostics.relativeRms(replace(development, frame=frame), 5)
    np.testing.assert_allclose(normalized.sensor_matrix(first)[:5], np.log(2))
    np.testing.assert_allclose(normalized.sensor_matrix(first)[5:], np.log(11))
    np.testing.assert_allclose(normalized.sensor_matrix(development.equipment_ids[1]), np.log(2))


def test_equipment_warnings_expose_alarm_concentration_hidden_by_pooling(development):
    config = development.config
    scorings, equipment = [], []
    for id, scores in [('noisy', np.ones(50)), ('quiet', np.zeros(1000)), ('short', np.zeros(20))]:
        rul = np.arange(len(scores), 0, -1)
        scoring = score_engine(id, scores, np.arange(len(scores)), rul, .5, config=config)
        scorings.append(scoring)
        equipment.append(diagnostics.equipmentSummary(scoring, scores, rul, config))
    result = diagnostics.cleanSummary(scorings, equipment, config)
    assert result['metrics']['early_alarm_burden'] < .05
    assert result['equipment_mean_burden'] > .4
    assert result['equipment_above_budget'] == ['noisy']
    assert result['equipment_without_early_window'] == ['short']


def test_nested_thresholds_and_preprocessing_never_see_outer_equipment(development, monkeypatch):
    ids = development.equipment_ids
    folds = [ids[index::3] for index in range(3)]
    splits = SplitAssignment(holdout=[], development=ids, folds=folds, seed=12, config_fingerprint=development.config.fingerprint())
    originalTrain, originalFit = diagnostics.train_development, diagnostics.fit_final
    seen = []

    def train(dataset, **kwargs):
        split = kwargs['splits']
        assert set(dataset.equipment_ids) == set(split.development)
        seen.append(set(split.development))
        return originalTrain(dataset, **kwargs)

    def fit(dataset, split, candidate, **kwargs):
        assert set(dataset.equipment_ids) == set(split.development)
        return originalFit(dataset, split, candidate, **kwargs)

    monkeypatch.setattr(diagnostics, 'train_development', train)
    monkeypatch.setattr(diagnostics, 'fit_final', fit)
    result = diagnostics.nestedClean(development, splits, LogisticRegressionCandidate('probe', {'max_iter': 300}))
    assert len(result['folds']) == 3 and result['metrics']['engines'] == len(ids)
    assert len(seen) == 3
    for index, row in enumerate(result['folds']):
        assert set(row['evaluation_ids']) == set(folds[index])
        assert not seen[index] & set(row['evaluation_ids'])
        assert set(row['threshold_ids']) == seen[index]
    assert {row['equipment_id'] for row in result['equipment']} == set(ids)


def test_nested_clean_refuses_invalid_grouping_and_too_few_folds(development):
    ids = development.equipment_ids
    for folds in ([ids[:4], ids[4:]], [ids[:4], ids[3:7], ids[7:]]):
        splits = SplitAssignment(holdout=[], development=ids, folds=folds, seed=12, config_fingerprint=development.config.fingerprint())
        with pytest.raises(ValueError):
            diagnostics.nestedClean(development, splits, LogisticRegressionCandidate('probe'))


def test_study_uses_only_context_development_subset(development, monkeypatch):
    ids = development.equipment_ids
    splits = SplitAssignment(holdout=ids[-1:], development=ids[:-1], folds=[ids[:-1][index::3] for index in range(3)],
        seed=12, config_fingerprint=development.config.fingerprint())
    training = train_development(development, config=development.config, splits=splits,
        candidates=[LogisticRegressionCandidate('probe', {'max_iter': 300})])
    training.dataset = development
    training.out_of_fold = {}
    inputs = []

    def nested(dataset, split, candidate):
        inputs.append(set(dataset.equipment_ids))
        assert set(dataset.equipment_ids) == set(split.development)
        assert not set(dataset.equipment_ids) & set(split.holdout)
        return {'metrics': {'engines': len(split.development)}}

    monkeypatch.setattr(diagnostics, 'nestedClean', nested)
    result = diagnostics.study(training, {'logistic_regression/probe': .5})
    assert len(inputs) == 2 and all(ids[-1] not in group for group in inputs)
    assert result['reserved_scored'] is False and result['independent_validation'] is False
    assert set(result['development_ids']) == set(ids[:-1])
    assert result['original_oof']['metrics']['engines'] == len(ids)-1


def test_cli_refuses_existing_output_before_loading_a_context(tmp_path, monkeypatch):
    output = tmp_path / 'existing'
    output.mkdir()
    monkeypatch.setattr(diagnostics, 'load_trusted_context', lambda *args, **kwargs: pytest.fail('Existing output must stop before model loading'))
    with pytest.raises(FileExistsError):
        diagnostics.main(['--context', str(tmp_path / 'unused'), '--trust-local-artifact', '--output', str(output)])
