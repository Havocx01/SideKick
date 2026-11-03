import json

import pytest

from app.faults.scenarios import fingerprint
from app.config import EXPERIMENT
from app.models.candidates import LogisticRegressionCandidate, XGBoostCandidate
from app.investigator.findings import FindingCriterion, classify
from scripts import evaluate_raw_vibration as study
from test_raw_fault_evaluator import evaluator, fault, rawContext as rawContext  # noqa: F401


def test_raw_study_cases_are_fixed_and_measurement_axes_only():
    cases = study.cases()
    assert len(cases) == len({case.scenario_id for case in cases}) == 8
    assert {atom.sensor for case in cases for atom in case.components} == {'horizontal', 'vertical'}
    assert {atom.onset_before_failure for case in cases for atom in case.components} == {30, 60}


def test_raw_case_checkpoints_resume_without_execution_and_reject_tampering(rawContext, tmp_path, monkeypatch):
    engine = evaluator(rawContext)
    case = fault()
    path = tmp_path / 'case.json'
    before = study.evaluateCase(engine, case, path)
    monkeypatch.setattr(engine, 'evaluate', lambda *_a: pytest.fail('Completed raw case executed again'))
    assert study.evaluateCase(engine, case, path).model_dump() == before.model_dump()
    saved = json.loads(path.read_text())
    saved['evaluation']['context_fingerprint'] = 'other'
    path.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match='checksum'):
        study.evaluateCase(engine, case, path)
    saved['digest'] = fingerprint(saved['evaluation'])
    path.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match='different fixed context'):
        study.evaluateCase(engine, case, path)


def test_raw_freeze_rejects_reserved_history_before_creating_output(tmp_path):
    features = tmp_path / 'features'
    features.mkdir()
    ids = [f'Bearing{condition}_{bearing}' for condition in range(1, 4) for bearing in range(1, 5)]
    ids[-1] = 'Bearing3_5'
    (features / 'protocol.json').write_text(json.dumps({'development': ids}))
    output = tmp_path / 'study'
    with pytest.raises(ValueError, match='twelve original development'):
        study.freeze(features, output, False)
    assert not output.exists()


def test_local_python_checkpoints_require_their_recorded_hash(tmp_path):
    path = tmp_path / 'local.joblib'
    study.saveObject(path, {'complete': True})
    assert study.loadObject(path) == {'complete': True}
    path.write_bytes(path.read_bytes() + b'tampered')
    with pytest.raises(ValueError, match='checksum'):
        study.loadObject(path)


def test_training_checkpoint_rejects_cross_arm_copies_and_wrong_model(rawContext, tmp_path):
    training = rawContext[0]
    path = tmp_path / 'model.joblib'
    metadata = {'arm': 'rich_lr', 'protocol': 'frozen', 'source': rawContext[1].fingerprint}
    study.saveObject(path, {'metadata': metadata, 'training': training})
    candidate = LogisticRegressionCandidate('raw-probe', {'max_iter': 300})
    assert study.loadTraining(path, metadata, training.dataset, training.splits, candidate).dataset.frame.equals(training.dataset.frame)
    with pytest.raises(ValueError, match='different diagnostic arm'):
        study.loadTraining(path, {**metadata, 'arm': 'rms_lr'}, training.dataset, training.splits, candidate)
    with pytest.raises(ValueError, match='declared model'):
        study.loadTraining(path, metadata, training.dataset, training.splits, XGBoostCandidate('raw-probe'))


def test_feature_helper_source_change_invalidates_frozen_resume(tmp_path, monkeypatch):
    features, output = tmp_path / 'features', tmp_path / 'study'
    (features / 'bearings').mkdir(parents=True)
    ids = [f'Bearing{condition}_{bearing}' for condition in range(1, 4) for bearing in range(1, 5)]
    protocol = {'development': ids, 'reserved_not_read': ['Bearing1_5', 'Bearing2_5', 'Bearing3_5'],
        'config': EXPERIMENT.as_dict(), 'folds': [ids[:4], ids[4:8], ids[8:]], 'lr': {'C': 1.}, 'xgb': {'max_depth': 4}}
    (features / 'protocol.json').write_text(json.dumps(protocol))
    (features / 'feature-check.json').write_text('{}')
    for id in ids:
        for suffix in ('csv', 'json'):
            (features / 'bearings' / f'{id}.{suffix}').write_text('fixture')
    study.freeze(features, output, False)
    study.freeze(features, output, True)
    originalHash = study.fileHash
    helper = study.Path(study.featureStudy.__file__)
    monkeypatch.setattr(study, 'fileHash', lambda path: 'changed-helper' if path == helper else originalHash(path))
    with pytest.raises(ValueError, match='exact frozen source'):
        study.freeze(features, output, True)


def test_completed_arm_rejects_a_different_protocol_or_context_without_executing(rawContext, tmp_path, monkeypatch):
    engine = evaluator(rawContext)
    metadata = {'arm': 'rich_lr', 'protocol': 'frozen', 'source': rawContext[1].fingerprint}
    candidate = next(iter(engine.thresholds))
    criterion = FindingCriterion(version=2, candidate=candidate, alarm_scope='per_equipment')
    values = [engine.evaluate(case) for case in study.cases()]
    result = {'metadata': metadata, 'context': engine.context_fingerprint, 'source': rawContext[1].fingerprint,
        'criterion': criterion.model_dump(mode='json'), 'checks': {}, 'evaluations': [value.model_dump(mode='json') for value in values],
        'findings': [classify(value, criterion).model_dump(mode='json') for value in values]}
    path = tmp_path / 'arm.json'
    study.writeJson(path, result)
    path.with_suffix(path.suffix + '.sha256').write_text(study.fileHash(path))
    monkeypatch.setattr(engine, 'evaluate', lambda *_a: pytest.fail('Completed arm ran a fault'))
    assert study.loadArm(path, metadata, engine, criterion, {}) == result
    with pytest.raises(ValueError, match='fixed context or protocol'):
        study.loadArm(path, {**metadata, 'arm': 'rich_xgb'}, engine, criterion, {})
    result['context'] = 'other'
    study.writeJson(path, result)
    path.with_suffix(path.suffix + '.sha256').write_text(study.fileHash(path))
    with pytest.raises(ValueError, match='fixed context or protocol'):
        study.loadArm(path, metadata, engine, criterion, {})


def test_completed_main_resume_reuses_all_arms_without_extraction_fits_or_faults(rawContext, tmp_path, monkeypatch):
    from app.faults.vibration import RawVibrationSource
    from scripts.evaluate_vibration_features import saveBearing

    training, source, _ = rawContext
    features, output = tmp_path / 'features', tmp_path / 'study'
    (features / 'bearings').mkdir(parents=True)
    frame = training.dataset.frame[['equipment_id', 'cycle', *training.dataset.sensors]].rename(columns={'cycle': 'cycle_index'})
    for id, records in source.recordings.items():
        sources = [{'path': row.path, 'sha256': row.sha256} for row in records]
        saveBearing(features / 'bearings', id, frame[frame.equipment_id == id], sources)
    frozen = {'config': training.config.as_dict(), 'development': training.splits.development,
        'folds': training.splits.folds, 'threshold': .5, 'lr': {'max_iter': 300}, 'xgb': {'n_estimators': 2, 'n_jobs': 1}}
    def freeze(features, directory, resume):
        if not resume:
            directory.mkdir()
        return frozen
    monkeypatch.setattr(study, 'freeze', freeze)
    monkeypatch.setattr(RawVibrationSource, 'prepare', lambda root, histories, dataset: source.forDataset(dataset))
    monkeypatch.setattr(study, 'checkSource', lambda *_a: None)
    args = ['--features', str(features), '--raw-root', str(source.root), '--output', str(output)]
    assert study.main(args) == 0
    paths = list(output.glob('*.json')) + list(output.glob('*.joblib'))
    before = {path.name: study.fileHash(path) for path in paths}
    def forbidden(*_a, **_k):
        pytest.fail('Completed diagnostic work restarted')
    monkeypatch.setattr(RawVibrationSource, 'prepare', forbidden)
    monkeypatch.setattr(RawVibrationSource, 'apply', forbidden)
    monkeypatch.setattr(study, 'train_development', forbidden)
    monkeypatch.setattr(study.featureStudy.np, 'loadtxt', forbidden)
    assert study.main([*args, '--resume']) == 0
    assert before == {path.name: study.fileHash(path) for path in paths}
    for name in ('rms_lr', 'rich_lr', 'rms_xgb', 'rich_xgb'):
        assert (output / f'{name}.joblib.sha256').is_file()
        assert (output / f'{name}.json.sha256').is_file()
