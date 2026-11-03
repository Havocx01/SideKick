from dataclasses import replace
import hashlib

import numpy as np
import pandas as pd
import pytest

from app.config import EXPERIMENT
from app.data.contract import build_dataset
from app.faults.evaluator import FixedDevelopmentEvaluator
from app.faults.scenarios import FaultCase, FaultPolicy
from app.features.vibration import extractVibration
from app.models.candidates import LogisticRegressionCandidate
from app.models.train import train_development
from app.schemas import ColumnMapping

MODEL = 'logistic_regression/raw-probe'


@pytest.fixture(scope='module')
def rawContext(tmp_path_factory):
    from app.faults.vibration import RawVibrationSource

    root = tmp_path_factory.mktemp('raw-context')
    config = replace(EXPERIMENT, holdout_engines=0, n_folds=2, feature_window=5, horizon_cycles=10,
        min_useful_lead=3, late_window_end=2, transition_band_end=15, configs_per_candidate=1)
    rows, histories = [], {}
    for equipment in range(4):
        id = f'RAW-{equipment}'
        histories[id] = []
        for cycle in range(1, 46):
            phase = np.arange(32) * 2*np.pi / 32
            amplitude = 1 + equipment*.1 + max(0, cycle-25)*.2
            samples = np.column_stack([amplitude*np.sin(phase*3), amplitude*np.cos(phase*5)])
            path = root / f'{id}-{cycle}.csv'
            np.savetxt(path, samples, delimiter=',', header='horizontal,vertical', comments='')
            histories[id].append({'path': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
            rows.append({'equipment_id': id, 'cycle_index': cycle, **extractVibration(samples)})
    frame = pd.DataFrame(rows)
    mapping = ColumnMapping(equipment_id='equipment_id', cycle_index='cycle_index', sensors=list(extractVibration(samples)))
    dataset = build_dataset(frame, mapping, dataset_id='raw-probe', source='Synthetic bursts', config=config)
    source = RawVibrationSource.prepare(root, histories, dataset, samplesPerRecording=32)
    training = train_development(dataset, config=config, candidates=[LogisticRegressionCandidate('raw-probe', {'max_iter': 300})])
    policy = FaultPolicy(allowed_sensors=('horizontal', 'vertical'), max_evaluations=128,
        assumptions='Synthetic raw accelerometer measurement faults; no physical validation.')
    return training, source, policy


def fault(sensor='horizontal', kind='dropout'):
    values = {'sensor': sensor, 'kind': kind, 'duration': 'persistent', 'onset_before_failure': 20}
    if kind == 'drift':
        values |= {'severity_sd': 1., 'sign': 1, 'ramp_cycles': 5}
    return FaultCase(components=[values])


def evaluator(context):
    training, source, policy = context
    return FixedDevelopmentEvaluator(training, {MODEL: .5}, policy, rawSource=source)


def test_raw_evaluator_rebuilds_all_features_with_fixed_models(rawContext, monkeypatch):
    engine = evaluator(rawContext)
    monkeypatch.setattr(LogisticRegressionCandidate, 'fit', lambda *_a, **_k: pytest.fail('Raw evaluation fitted a model'))
    training, source, _ = rawContext
    fold = training.folds[0]
    equipment = fold.validation_engines[0]
    block = fold.blocks[equipment]
    case = fault()
    application = source.apply(equipment, block.rul, case, fold.builder, training.config,
        rawScale=source.scale(fold.train_engines, training.dataset))
    actual, components = engine._inject(engine._prepared[0][0], engine._prepared[0][1][equipment], equipment, case)
    np.testing.assert_array_equal(actual, fold.builder.build_engine(application.values))
    assert len(components) == 1
    result = engine.evaluate(case)
    assert result.status == 'complete' and result.evaluated_histories == 4
    assert result.raw_source['fingerprint'] == source.fingerprint
    assert result.raw_source['domain'] == 'raw_vibration'
    assert str(source.root) not in str(result.model_dump(mode='json'))
    assert engine.evaluate(case).model_dump() == result.model_dump()


def test_raw_context_and_threshold_remedy_preserve_measurement_domain(rawContext):
    from app.investigator.remedies import augmentedRemedy, thresholdRemedy

    engine = evaluator(rawContext)
    remedy, _ = thresholdRemedy(engine, MODEL, .7)
    assert remedy.rawSource.fingerprint == engine.rawSource.fingerprint
    assert remedy.context_fingerprint != engine.context_fingerprint
    result = remedy.evaluate(fault(kind='drift'))
    assert result.raw_source == engine.evaluate(fault(kind='drift')).raw_source
    with pytest.raises(ValueError, match='raw'):
        augmentedRemedy(engine, approveTraining=True)


def test_raw_replay_is_exact_and_requires_unchanged_source(rawContext, tmp_path):
    from app.faults.replay import export_evaluation, replay_evaluation

    engine = evaluator(rawContext)
    result = engine.evaluate(fault())
    directory = tmp_path / 'replay'
    export_evaluation(engine, result, directory)
    assert replay_evaluation(directory, trusted=True).model_dump() == result.model_dump()
    path = rawContext[1].root / 'RAW-0-40.csv'
    before = path.read_bytes()
    try:
        path.write_bytes(before + b'\n')
        with pytest.raises(ValueError, match='checksum|changed|hash'):
            replay_evaluation(directory, trusted=True)
    finally:
        path.write_bytes(before)


def test_raw_transfer_and_fresh_csv_validation_fail_before_execution(rawContext, tmp_path):
    from app.faults.remote import RemoteExecutor, RemoteJobError
    from app.faults.replay import export_evaluation
    from app.investigator.validation import freshContext, knownExposures

    engine = evaluator(rawContext)
    directory = tmp_path / 'context'
    export_evaluation(engine, engine.evaluate(fault()), directory)
    with pytest.raises(RemoteJobError, match='raw'):
        RemoteExecutor(engine, directory, tmp_path / 'out', tmp_path / 'in', transferConsent=True)
    with pytest.raises(ValueError, match='raw'):
        freshContext(engine, rawContext[0].dataset)
    assert set(rawContext[1].historyIds.values()) <= set(knownExposures(engine))


def test_raw_runner_reduction_remedy_and_public_evidence_keep_the_same_domain(rawContext, tmp_path):
    import json

    from app.faults.investigation import ExperimentRunner, InvestigationBudget, InvestigationStore
    from app.investigator.findings import FindingCriterion, recordFindings, saveCriterion
    from app.investigator.publication import publicExport
    from app.investigator.reduction import reduce
    from app.investigator.remedies import compareRemedy

    engine = evaluator(rawContext)
    case = FaultCase(components=[fault().components[0], fault('vertical').components[0]])
    store = InvestigationStore(tmp_path / 'store')
    id = store.create(engine, InvestigationBudget(max_experiments=8), [case.model_dump(mode='json')])
    saveCriterion(store, id, FindingCriterion(version=2, candidate=MODEL, alarm_scope='per_equipment', min_histories=1))
    summary = ExperimentRunner(store, engine).run(id)
    assert summary.failures == 0 and len(summary.completed) == 1
    finding = recordFindings(store, id)[0]
    assert finding.is_discovery, finding.model_dump_json()
    reduction = reduce(store, engine, summary.completed[0], maxExperiments=3)
    assert reduction['status'] in {'complete', 'partial'}
    assert all('raw accelerometer' in text for text in finding.assumptions)
    report = compareRemedy(store, engine, id, 'threshold', threshold=.4)
    assert report['originalContext'] == engine.context_fingerprint
    public = publicExport(store, id)
    text = json.dumps(public)
    assert 'raw accelerometer' in text and str(rawContext[1].root) not in text
    assert all(f'"{id}"' not in text for id in rawContext[1].historyIds)


def test_raw_controller_receives_measurement_semantics_without_private_source_details(rawContext, tmp_path):
    import json

    from app.config import Settings
    from app.faults.investigation import InvestigationBudget, InvestigationStore
    from app.investigator.controller import ControllerLimits, NemotronController
    from app.investigator.findings import FindingCriterion, saveCriterion

    engine = evaluator(rawContext)
    store = InvestigationStore(tmp_path / 'store')
    id = store.create(engine, InvestigationBudget(max_experiments=4))
    saveCriterion(store, id, FindingCriterion(version=2, candidate=MODEL, alarm_scope='per_equipment'))
    controller = NemotronController(store, engine, Settings(mode='full'))
    packet = controller.packet(store.get(id), ControllerLimits())
    assert packet['measurement']['domain'] == 'raw_vibration'
    assert 'prior' in packet['measurement']['stuck'] or 'preceding' in packet['measurement']['stuck']
    text = json.dumps(packet)
    assert str(rawContext[1].root) not in text
    assert all(f'"{id}"' not in text for id in rawContext[1].historyIds)
    assert 'horizontal' not in text and 'vertical' not in text


def test_raw_preview_stops_before_reading_after_cancellation(rawContext, monkeypatch):
    engine = evaluator(rawContext)
    reads, checkpoints = [], []
    from app.faults.vibration import RawVibrationSource

    original = RawVibrationSource._read
    def read(source, record, **options):
        reads.append(record.path)
        return original(source, record, **options)
    def check():
        checkpoints.append(True)
        if len(checkpoints) == 2:
            raise RuntimeError('cancelled')
    monkeypatch.setattr(RawVibrationSource, '_read', read)
    with pytest.raises(RuntimeError, match='cancelled'):
        engine.preview(fault(), check=check)
    assert len(reads) == 1


def test_raw_preview_enforces_its_own_cooperative_deadline(rawContext, monkeypatch):
    from app.faults import evaluator as module
    from app.faults.evaluator import EvaluationStopped

    engine = evaluator(rawContext)
    clock = [0.]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    def check():
        clock[0] += engine.policy.max_seconds
    with pytest.raises(EvaluationStopped, match='preview'):
        engine.preview(fault(), check=check)


def test_raw_controller_cancellation_during_preview_saves_no_proposal(rawContext, tmp_path, monkeypatch):
    import asyncio

    from app.config import Settings
    from app.faults.investigation import InvestigationBudget, InvestigationStore
    from app.faults.vibration import RawVibrationSource
    from app.investigator.controller import ControllerLimits, NemotronController, controllerStatus
    from test_nemotron_controller import proposal, provider

    engine = evaluator(rawContext)
    store = InvestigationStore(tmp_path / 'store')
    id = store.create(engine, InvestigationBudget(max_experiments=4))
    calls = provider(monkeypatch, [proposal(onset_before_failure=20)])
    settings = Settings(mode='full', assistant_model='nvidia/nemotron-3-super-120b-a12b', nebius_api_key='mock',
        nebius_reasoning_tokens=0, assistant_live_enabled=True)
    cancelled, reads = [False], []
    original = RawVibrationSource._read
    def read(source, record, **options):
        values = original(source, record, **options)
        reads.append(record.path)
        cancelled[0] = True
        return values
    monkeypatch.setattr(RawVibrationSource, '_read', read)
    controller = NemotronController(store, engine, settings, ControllerLimits(maxCalls=1))
    report = asyncio.run(controller.run(id, allowProvider=True, cancelled=lambda: cancelled[0]))
    assert report['stopReason'] == 'cancelled' and report['experimentsUsed'] == 0
    assert len(calls) == len(reads) == 1
    assert store.load(id).proposals == []
    assert controllerStatus(store, id)['calls'][0]['status'] == 'cancelled'
