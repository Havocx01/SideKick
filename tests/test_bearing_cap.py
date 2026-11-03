from dataclasses import replace
import importlib.util
from pathlib import Path

import numpy as np
import pytest

from app.config import EXPERIMENT
from app.models.train import EngineScores, train_development
from app.schemas import SplitAssignment
from test_clean_alarm_diagnostics import development as development  # noqa: F401

spec = importlib.util.spec_from_file_location('bearingCap', Path(__file__).parents[1] / 'scripts/evaluate_bearing_cap.py')
capped = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capped)

CONFIG = replace(EXPERIMENT, feature_window=5, n_folds=3, holdout_engines=0, horizon_cycles=20,
    min_useful_lead=5, late_window_end=4, transition_band_end=40, min_detection_fraction=.8, max_early_alarm_burden=.05)


def history(id, scores):
    scores = np.asarray(scores, dtype=float)
    rul = np.arange(len(scores), 0, -1)
    return EngineScores(id, np.arange(len(scores)), rul, scores, (rul <= CONFIG.horizon_cycles).astype(int))


def timely(id='one', length=80):
    scores = np.full(length, .1)
    scores[-20:] = .9
    return history(id, scores)


def test_selects_a_feasible_threshold_and_rejects_never_alert_as_a_fix():
    choice = capped.chooseCapped({'one': timely()}, CONFIG)
    assert choice['qualified'] and choice['threshold'] == .9
    assert choice['selected']['metrics']['detection_fraction'] == 1
    assert choice['selected']['equipment_max_burden'] == 0
    failed = capped.chooseCapped({'one': history('one', np.full(80, .9))}, CONFIG)
    assert not failed['qualified'] and failed['threshold'] is None
    assert failed['best_capped']['metrics']['detection_fraction'] == 0
    assert 'warning_requirement_not_met' in failed['reasons']


def test_per_bearing_cap_rejects_alarm_concentration_hidden_by_pooling():
    noisy = timely('noisy')
    noisy.scores[:10] = .9
    perEngine = {'noisy': noisy, 'long': timely('long', 2000)}
    pooled = capped.calibrationAt(perEngine, .9, CONFIG)
    assert pooled['metrics']['early_alarm_burden'] < .05
    assert pooled['equipment_max_burden'] > .05
    assert pooled['metrics']['detection_fraction'] == 1
    choice = capped.chooseCapped(perEngine, CONFIG)
    assert not choice['qualified'] and choice['threshold'] is None


def test_cap_is_inclusive_and_missing_windows_are_not_a_pass():
    row = timely()
    row.scores[:2] = .9
    choice = capped.chooseCapped({'one': row}, CONFIG)
    assert choice['qualified']
    assert choice['selected']['equipment_max_burden'] == pytest.approx(.05)
    missing = capped.chooseCapped({'long': timely('long'), 'short': timely('short', 25)}, CONFIG)
    assert not missing['qualified'] and missing['threshold'] is None
    assert missing['best_capped']['metrics']['detection_fraction'] == 1
    assert missing['missing_early_windows'] == ['short']
    assert 'missing_early_window_coverage' in missing['reasons']


def test_all_missing_windows_and_empty_calibration_are_explicit():
    result = capped.chooseCapped({'short': timely('short', 25)}, CONFIG)
    assert result['threshold'] is None and result['best_capped'] is None
    assert result['reasons'] == ['no_eligible_early_window']
    with pytest.raises(ValueError, match='empty'):
        capped.chooseCapped({}, CONFIG)


@pytest.mark.parametrize('continuous', [False, True])
def test_binary_search_matches_exhaustive_breakpoints_with_persistence_and_gaps(continuous):
    generator = np.random.default_rng(91)
    config = replace(CONFIG, max_early_alarm_burden=.3, min_detection_fraction=.5)
    for _ in range(12):
        rows = {str(index): history(str(index), generator.random(80) if continuous else generator.choice([.1, .4, .7, .9], 80)) for index in range(3)}
        rows['0'].cycles[30:] += 2
        rows['0'].scores[7] = np.nan
        values = np.unique(np.concatenate([row.scores[np.isfinite(row.scores)] for row in rows.values()]))
        thresholds = np.append(values, np.nextafter(values[-1], np.inf))
        feasible = [(float(value), capped.calibrationAt(rows, float(value), config)) for value in thresholds]
        feasible = [(value, result) for value, result in feasible if result['equipment_max_burden'] <= config.max_early_alarm_burden]
        expectedThreshold, expected = max(feasible, key=lambda pair: (pair[1]['metrics']['detected'], pair[0]))
        choice = capped.chooseCapped(rows, config)
        assert choice['diagnostic_threshold'] == expectedThreshold
        assert choice['best_capped']['metrics'] == expected['metrics']
        assert choice['qualified'] == (expected['metrics']['detection_fraction'] >= config.min_detection_fraction)


def test_rejected_folds_never_fit_or_score_an_outer_model(development, monkeypatch):
    ids = development.equipment_ids
    splits = SplitAssignment(holdout=[], development=ids, folds=[ids[index::3] for index in range(3)], seed=12,
        config_fingerprint=development.config.fingerprint())
    choices = []

    def reject(perEngine, config):
        choices.append(set(perEngine))
        return {'qualified': False, 'threshold': None, 'reasons': ['warning_requirement_not_met'], 'best_capped': None}

    monkeypatch.setattr(capped, 'chooseCapped', reject)
    monkeypatch.setattr(capped, 'fit_final', lambda *args, **kwargs: pytest.fail('Rejected outer group must not be fitted'))
    monkeypatch.setattr(capped.diagnostics, 'scoreDesign', lambda *args, **kwargs: pytest.fail('Rejected outer group must not be scored'))
    result = capped.nestedCapped(development, splits, capped.LogisticRegressionCandidate('probe', {'max_iter': 300}))
    assert result['metrics'] is None and result['evaluated_histories'] == 0 and result['expected_histories'] == len(ids)
    assert result['qualified_folds'] == 0
    for choice, fold in zip(choices, result['folds'], strict=True):
        assert choice == set(fold['threshold_ids'])
        assert not choice & set(fold['evaluation_ids'])


def test_cli_refuses_old_output_before_loading_context(tmp_path, monkeypatch):
    monkeypatch.setattr(capped, 'load_trusted_context', lambda *args, **kwargs: pytest.fail('Must not load a model'))
    with pytest.raises(FileExistsError):
        capped.main(['--context', str(tmp_path), '--trust-local-artifact', '--output', str(tmp_path)])


def test_admitted_groups_fit_on_training_and_score_only_their_outer_members(development, monkeypatch):
    ids = development.equipment_ids
    splits = SplitAssignment(holdout=[], development=ids, folds=[ids[index::3] for index in range(3)], seed=12,
        config_fingerprint=development.config.fingerprint())
    originalFit, originalScore = capped.fit_final, capped.diagnostics.scoreDesign
    calibrations, fits, evaluations = [], [], []

    def admit(perEngine, config):
        calibrations.append(set(perEngine))
        return {'qualified': True, 'threshold': .5, 'reasons': [], 'best_capped': None}

    def fit(dataset, split, candidate, **kwargs):
        assert set(dataset.equipment_ids) == set(split.development)
        fits.append(set(dataset.equipment_ids))
        return originalFit(dataset, split, candidate, **kwargs)

    def score(model, builder, dataset, threshold):
        evaluations.append(set(dataset.equipment_ids))
        assert threshold == .5
        return originalScore(model, builder, dataset, threshold)

    monkeypatch.setattr(capped, 'chooseCapped', admit)
    monkeypatch.setattr(capped, 'fit_final', fit)
    monkeypatch.setattr(capped.diagnostics, 'scoreDesign', score)
    result = capped.nestedCapped(development, splits, capped.LogisticRegressionCandidate('probe', {'max_iter': 300}))
    assert result['qualified_folds'] == 3 and result['complete_evaluation']
    assert result['evaluated_histories'] == result['metrics']['engines'] == len(ids)
    for index, fold in enumerate(result['folds']):
        assert calibrations[index] == fits[index] == set(fold['threshold_ids'])
        assert evaluations[index] == set(fold['evaluation_ids'])
        assert not evaluations[index] & fits[index]


def test_study_removes_a_context_holdout_before_transforming_or_training(development, monkeypatch):
    ids = development.equipment_ids
    splits = SplitAssignment(holdout=ids[-1:], development=ids[:-1], folds=[ids[:-1][index::3] for index in range(3)], seed=12,
        config_fingerprint=development.config.fingerprint())
    training = train_development(development, config=development.config, splits=splits,
        candidates=[capped.LogisticRegressionCandidate('probe', {'max_iter': 300})])
    training.dataset = development
    seen = []

    def nested(dataset, current, candidate):
        assert set(dataset.equipment_ids) == set(current.development)
        assert ids[-1] not in dataset.equipment_ids
        seen.append(type(candidate))
        return {'expected_histories': len(current.development), 'evaluated_histories': 0}

    monkeypatch.setattr(capped, 'nestedCapped', nested)
    result = capped.study(training)
    assert len(seen) == 4
    assert seen == [capped.LogisticRegressionCandidate, capped.balanced.EquipmentBalancedLR] * 2
    assert result['development_ids'] == ids[:-1]
    assert not result['reserved_scored'] and not result['independent_validation']
