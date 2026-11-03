from dataclasses import replace
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.config import EXPERIMENT
from app.models.candidates import XGBoostCandidate
from app.schemas import SplitAssignment
from test_clean_alarm_diagnostics import development as development  # noqa: F401

spec = importlib.util.spec_from_file_location('vibrationStudy', Path(__file__).parents[1] / 'scripts/evaluate_vibration_features.py')
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)


def test_extraction_reads_only_the_requested_development_bearing(tmp_path):
    source = tmp_path / 'source'
    directory = source / 'condition/Bearing1_1'
    directory.mkdir(parents=True)
    samples = np.tile([3., -4.], (8, 1))
    for index in range(1, 4):
        np.savetxt(directory / f'{index}.csv', samples, delimiter=',', header='horizontal,vertical', comments='')
    reserved = source / 'condition/Bearing1_5'
    reserved.mkdir()
    (reserved / '1.csv').write_text('invalid reserved input must never be parsed')
    frame, manifest = study.extractBearing(source, 'Bearing1_1', 3, expectedSamples=8)
    assert len(frame) == len(manifest) == 3
    assert set(frame.equipment_id) == {'Bearing1_1'}
    np.testing.assert_allclose(frame.horizontal_rms, 3.)
    np.testing.assert_allclose(frame.vertical_rms, 4.)
    assert all('Bearing1_1' in row['path'] and len(row['sha256']) == 64 for row in manifest)
    with pytest.raises(ValueError, match='development'):
        study.extractBearing(source, 'Bearing1_5', 1, expectedSamples=8)


def test_missing_or_malformed_recordings_fail_without_inventing_features(tmp_path):
    directory = tmp_path / 'condition/Bearing1_1'
    directory.mkdir(parents=True)
    np.savetxt(directory / '2.csv', np.ones((8, 2)), delimiter=',', header='horizontal,vertical', comments='')
    with pytest.raises(ValueError, match='consecutive'):
        study.extractBearing(tmp_path, 'Bearing1_1', 1, expectedSamples=8)
    (directory / '2.csv').rename(directory / '1.csv')
    with pytest.raises(ValueError, match='samples'):
        study.extractBearing(tmp_path, 'Bearing1_1', 1, expectedSamples=9)


def test_dataset_preserves_histories_and_selects_only_requested_features():
    rows = []
    for id in ('Bearing1_1', 'Bearing1_2', 'Bearing2_1'):
        for index in range(1, 81):
            rows.append({'equipment_id': id, 'cycle_index': index, 'horizontal_rms': 1., 'vertical_rms': 2., 'horizontal_kurtosis': 3.})
    frame = pd.DataFrame(rows)
    config = replace(EXPERIMENT, holdout_engines=0, n_folds=3, feature_window=5)
    dataset = study.makeDataset(frame, ['horizontal_rms', 'vertical_rms'], config)
    assert dataset.sensors == ['horizontal_rms', 'vertical_rms']
    assert set(dataset.equipment_ids) == set(frame.equipment_id)
    assert dataset.failure_cycles == dict.fromkeys(dataset.equipment_ids, 80)
    assert not dataset.scorable_mask()[79]


def test_cached_bearing_rejects_changed_feature_bytes(tmp_path):
    frame = pd.DataFrame({'equipment_id': ['Bearing1_1'], 'cycle_index': [1], 'horizontal_rms': [2.]})
    study.saveBearing(tmp_path, 'Bearing1_1', frame, [{'path': 'source.csv', 'sha256': 'a'*64}])
    saved = study.loadBearing(tmp_path, 'Bearing1_1')
    assert saved.equipment_id.tolist() == ['Bearing1_1']
    (tmp_path / 'Bearing1_1.csv').write_text('tampered')
    with pytest.raises(ValueError, match='checksum'):
        study.loadBearing(tmp_path, 'Bearing1_1')


@pytest.fixture
def cachedStudy(tmp_path, monkeypatch):
    ids = [f'Bearing{condition}_{index}' for condition in range(1, 4) for index in range(1, 5)]
    config = replace(EXPERIMENT, holdout_engines=0, n_folds=3, feature_window=5, horizon_cycles=30,
        min_useful_lead=10, late_window_end=5, transition_band_end=45, min_detection_fraction=.8, max_early_alarm_burden=.05)
    protocol = {'development': ids, 'reserved': [f'Bearing{condition}_5' for condition in range(1, 4)],
        'recordings': dict.fromkeys(ids, 80), 'samples_per_recording': 32768, 'sampling_hz': 25600}
    baseline = {'config': config.as_dict(), 'variants': {'raw_rms': {'folds': [{'evaluation_ids': ids[index::3]} for index in range(3)]}}}
    inputs = {'protocol': protocol, 'baseline': baseline, 'sources': {'files': []}}
    for name, value in inputs.items():
        (tmp_path / f'{name}.json').write_text(json.dumps(value))
    features = study.featureSchema()
    frames = {id: pd.DataFrame([{'equipment_id': id, 'cycle_index': index, **dict.fromkeys(features, 1.)} for index in range(1, 81)]) for id in ids}
    pd.concat(frames.values()).to_csv(tmp_path / 'reference.csv', index=False)
    monkeypatch.setattr(study, 'extractBearing', lambda source, id, recordings, **kwargs: (frames[id], []))
    calls = []

    def pooled(dataset, splits, candidate):
        calls.append(candidate)
        return {'metrics': {'engines': 12, 'detected': 0, 'early_alarm_burden': 0.}, 'equipment_max_burden': 0., 'clean_limits_met': False}

    monkeypatch.setattr(study.diagnostics, 'nestedClean', pooled)
    monkeypatch.setattr(study.capped, 'nestedCapped', lambda *args: {'qualified_folds': 0, 'total_folds': 3})
    output = tmp_path / 'result'
    args = ['--raw-root', str(tmp_path / 'unused'), '--protocol', str(tmp_path / 'protocol.json'), '--baseline', str(tmp_path / 'baseline.json'),
        '--reference', str(tmp_path / 'reference.csv'), '--source-manifest', str(tmp_path / 'sources.json'), '--output', str(output)]
    assert study.main(args) == 0
    assert len(calls) == 4 and sum(isinstance(candidate, XGBoostCandidate) for candidate in calls) == 2
    assert all(candidate.params['n_estimators'] == 300 for candidate in calls if isinstance(candidate, XGBoostCandidate))
    return args, output


def test_resume_reuses_verified_features_and_arms_without_fitting_or_parsing(cachedStudy, monkeypatch):
    args, output = cachedStudy
    digest = study.fileHash(output / 'results.json')
    monkeypatch.setattr(study, 'extractBearing', lambda *args, **kwargs: pytest.fail('No repeated raw parsing'))
    monkeypatch.setattr(study.diagnostics, 'nestedClean', lambda *args, **kwargs: pytest.fail('No repeated model fits'))
    monkeypatch.setattr(study.capped, 'nestedCapped', lambda *args, **kwargs: pytest.fail('No repeated threshold fits'))
    assert study.main(args + ['--resume']) == 0
    assert study.fileHash(output / 'results.json') == digest


@pytest.mark.parametrize('changed', ['protocol', 'arm'])
def test_resume_refuses_changed_protocol_or_completed_arm(cachedStudy, monkeypatch, changed):
    args, output = cachedStudy
    target = output / ('protocol.json' if changed == 'protocol' else 'rms_lr.json')
    target.write_text('{}')
    monkeypatch.setattr(study, 'extractBearing', lambda *args, **kwargs: pytest.fail('No raw parsing on failed resume'))
    monkeypatch.setattr(study.diagnostics, 'nestedClean', lambda *args, **kwargs: pytest.fail('No fitting on failed resume'))
    with pytest.raises(ValueError, match='exact frozen|checksum'):
        study.main(args + ['--resume'])


def test_grouped_xgboost_executes_the_same_nested_interface(development):
    ids = development.equipment_ids
    splits = SplitAssignment(holdout=[], development=ids, folds=[ids[index::3] for index in range(3)], seed=12,
        config_fingerprint=development.config.fingerprint())
    candidate = XGBoostCandidate('probe', {'n_estimators': 5, 'max_depth': 2, 'model_seed': 12, 'n_jobs': 1})
    result = study.diagnostics.nestedClean(development, splits, candidate)
    assert result['metrics']['engines'] == len(ids)
    for fold in result['folds']:
        assert not set(fold['threshold_ids']) & set(fold['evaluation_ids'])
