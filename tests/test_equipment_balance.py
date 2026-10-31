from dataclasses import replace
import importlib.util
from pathlib import Path

import numpy as np
import pytest

from app.models.base import DesignMatrix
from app.models.candidates import LogisticRegressionCandidate
from app.models.train import train_development
from app.schemas import SplitAssignment
from test_clean_alarm_diagnostics import development as development  # noqa: F401

spec = importlib.util.spec_from_file_location('equipmentBalance', Path(__file__).parents[1] / 'scripts/evaluate_equipment_balance.py')
balanced = importlib.util.module_from_spec(spec)
spec.loader.exec_module(balanced)


def design():
    equipment = np.array(['long'] * 10 + ['short'] * 2)
    labels = np.array([0] * 8 + [1] * 2 + [0, 1])
    values = np.array([0.] * 10 + [100., 100.])[:, None]
    return DesignMatrix(X=values, y=labels, cycle=np.arange(12), equipment_id=equipment, rul=np.arange(12), rows=np.arange(12), feature_names=['rms'])


def test_weights_balance_equipment_and_its_observed_classes():
    data = design()
    weights = balanced.equipmentWeights(data)
    assert weights.mean() == pytest.approx(1.)
    assert np.isfinite(weights).all() and (weights > 0).all()
    for equipment in ('long', 'short'):
        assert weights[data.equipment_id == equipment].sum() == pytest.approx(6.)
        for label in (0, 1):
            assert weights[(data.equipment_id == equipment) & (data.y == label)].sum() == pytest.approx(3.)


def test_one_class_equipment_keeps_its_mass_and_invalid_labels_fail():
    data = design()
    labels = data.y.copy()
    labels[data.equipment_id == 'short'] = 0
    weights = balanced.equipmentWeights(replace(data, y=labels))
    assert weights[data.equipment_id == 'short'].sum() == pytest.approx(6.)
    assert weights[labels == 0].sum() == pytest.approx(9.)
    for invalid in (np.full(12, 2), np.full(12, np.nan)):
        with pytest.raises(ValueError, match='binary'):
            balanced.equipmentWeights(replace(data, y=invalid))
    with pytest.raises(ValueError, match='empty'):
        balanced.equipmentWeights(data.select(np.zeros(12, dtype=bool)))


def test_real_pipeline_weights_scaling_and_does_not_double_balance_classes():
    data = design()
    model = balanced.EquipmentBalancedLR('weighted', {'max_iter': 300})
    model.fit(data)
    assert model.fitted
    assert model._pipeline.named_steps['scale'].mean_[0] == pytest.approx(50.)
    assert model._pipeline.named_steps['model'].class_weight is None
    np.testing.assert_allclose(model.score(data), .5, atol=1e-8)
    assert set(model.feature_importance()) == {'rms'}


def test_nested_fits_preserve_weighted_candidate_and_training_only_members(development, monkeypatch):
    ids = development.equipment_ids
    splits = SplitAssignment(holdout=[], development=ids, folds=[ids[index::3] for index in range(3)], seed=12,
        config_fingerprint=development.config.fingerprint())
    original = balanced.EquipmentBalancedLR.fit
    fitted = []

    def fit(self, data, **kwargs):
        fitted.append(set(data.equipment_id))
        return original(self, data, **kwargs)

    monkeypatch.setattr(balanced.EquipmentBalancedLR, 'fit', fit)
    result = balanced.diagnostics.nestedClean(development, splits, balanced.EquipmentBalancedLR('probe', {'max_iter': 300}))
    assert len(fitted) == 9
    assert result['metrics']['engines'] == len(ids)
    for index, fold in enumerate(result['folds']):
        evaluation = set(fold['evaluation_ids'])
        for group in fitted[index*3:index*3+3]:
            assert not group & evaluation
            assert group <= set(fold['threshold_ids'])


def test_four_arm_study_excludes_context_holdout_before_any_transform_or_training(development, monkeypatch):
    ids = development.equipment_ids
    splits = SplitAssignment(holdout=ids[-1:], development=ids[:-1], folds=[ids[:-1][index::3] for index in range(3)], seed=12,
        config_fingerprint=development.config.fingerprint())
    training = train_development(development, config=development.config, splits=splits, candidates=[LogisticRegressionCandidate('probe')])
    training.dataset = development
    calls = []

    def nested(dataset, current, candidate):
        assert set(dataset.equipment_ids) == set(current.development)
        assert ids[-1] not in dataset.equipment_ids
        calls.append(type(candidate))
        return {'metrics': {'engines': len(current.development)}, 'clean_limits_met': True,
            'equipment_above_budget': [], 'equipment_without_early_window': ['no-window']}

    monkeypatch.setattr(balanced.diagnostics, 'nestedClean', nested)
    result = balanced.study(training)
    assert calls == [LogisticRegressionCandidate, balanced.EquipmentBalancedLR, LogisticRegressionCandidate, balanced.EquipmentBalancedLR]
    assert len(result['variants']) == 4
    assert not result['reserved_scored'] and not result['independent_validation']
    assert all(not row['complete_equipment_coverage'] for row in result['variants'].values())


def test_cli_refuses_existing_output_before_context_loading(tmp_path, monkeypatch):
    monkeypatch.setattr(balanced, 'load_trusted_context', lambda *args, **kwargs: pytest.fail('Should stop before loading'))
    with pytest.raises(FileExistsError):
        balanced.main(['--context', str(tmp_path), '--trust-local-artifact', '--output', str(tmp_path)])
