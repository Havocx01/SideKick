from dataclasses import replace
import hashlib

import numpy as np
import pandas as pd
import pytest

from app.config import EXPERIMENT
from app.data.contract import build_dataset
from app.faults.scenarios import FaultCase
from app.faults.vibration import RawVibrationSource
from app.features.build import FeatureBuilder, Preprocessor
from app.features.vibration import extractVibration, featureSchema
from app.schemas import ColumnMapping


CONFIG = replace(EXPERIMENT, feature_window=2, horizon_cycles=3, min_useful_lead=1, late_window_end=0,
    transition_band_end=4, holdout_engines=0, n_folds=2)


def case(sensor='horizontal', **values):
    atom = {'sensor': sensor, 'kind': 'dropout', 'duration': 'persistent', 'onset_before_failure': 4, **values}
    return FaultCase(components=[atom])


def datasetFor(rows, sensors=None):
    sensors = list(sensors or featureSchema())
    mapping = ColumnMapping(equipment_id='equipment_id', cycle_index='cycle_index', sensors=sensors, failure_cycle=None, inferred=False)
    return build_dataset(pd.DataFrame(rows)[['equipment_id', 'cycle_index', *sensors]], mapping,
        dataset_id='raw-fixture', source='Synthetic bursts', config=CONFIG)


@pytest.fixture
def raw(tmp_path):
    rows, histories, bursts = [], {}, {}
    for id, amplitude in [('train', 1.), ('test', 3.)]:
        histories[id], bursts[id] = [], []
        for cycle in range(1, 9):
            samples = np.column_stack([np.arange(32) * amplitude + cycle, np.sin(np.arange(32)) * (cycle+1)])
            path = tmp_path / id / f'{cycle}.csv'
            path.parent.mkdir(exist_ok=True)
            np.savetxt(path, samples, delimiter=',', header='horizontal,vertical', comments='', fmt='%.17g')
            histories[id].append({'path': path.relative_to(tmp_path).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
            bursts[id].append(samples)
            rows.append({'equipment_id': id, 'cycle_index': cycle, **extractVibration(samples)})
    dataset = datasetFor(rows)
    source = RawVibrationSource.prepare(tmp_path, histories, dataset, samplesPerRecording=32)
    builder = FeatureBuilder(Preprocessor.fit(dataset), CONFIG)
    return source, dataset, builder, histories, bursts, rows


def apply(raw, scenario, **kwargs):
    source, dataset, builder, *_ = raw
    rul = dataset.frame[dataset.frame.equipment_id == 'test'].rul.to_numpy()
    return source.apply('test', rul, scenario, builder, CONFIG, rawScale=source.scale(['train'], dataset), **kwargs)


def test_raw_dropout_marks_every_axis_feature_and_keeps_other_axis(raw):
    source, dataset, _, _, bursts, _ = raw
    before = dataset.sensor_matrix('test').copy()
    result = apply(raw, case())
    assert result.applied and result.components[0].onset_index == 3
    horizontal = [i for i, name in enumerate(source.featureNames) if name.startswith('horizontal_')]
    vertical = [i for i, name in enumerate(source.featureNames) if name.startswith('vertical_')]
    assert np.isnan(result.values[3:, horizontal]).all()
    np.testing.assert_array_equal(result.values[:3], before[:3])
    np.testing.assert_array_equal(result.values[:, vertical], before[:, vertical])
    np.testing.assert_array_equal(dataset.sensor_matrix('test'), before)
    np.testing.assert_array_equal(bursts['test'][0][:, 0], np.arange(32)*3+1)


def test_stuck_digitizer_holds_previous_sample_instead_of_previous_rms(raw):
    source, _, _, _, bursts, _ = raw
    result = apply(raw, case(kind='stuck'))
    expected = bursts['test'][3].copy()
    expected[:, 0] = bursts['test'][2][-1, 0]
    features = extractVibration(expected)
    np.testing.assert_allclose(result.values[3], [features[name] for name in source.featureNames])
    assert result.values[3, source.featureNames.index('horizontal_rms')] == bursts['test'][2][-1, 0]
    assert result.values[3, source.featureNames.index('horizontal_band_low_energy')] == 0


def test_offset_drift_reextracts_correlated_features_using_training_raw_scale(raw):
    source, dataset, _, _, bursts, _ = raw
    scale = source.scale(['train'], dataset)
    expectedScale = np.concatenate(bursts['train'][1:7]).std(axis=0)
    np.testing.assert_allclose(list(scale.values()), expectedScale)
    result = apply(raw, case(kind='drift', severity_sd=2., sign=-1, ramp_cycles=2))
    for index, progress in [(3, .5), (4, 1.), (7, 1.)]:
        expected = bursts['test'][index].copy()
        expected[:, 0] -= 2*scale['horizontal']*progress
        features = extractVibration(expected)
        np.testing.assert_allclose(result.values[index], [features[name] for name in source.featureNames], atol=1e-12)


def test_training_scale_ignores_validation_warmup_and_failure_target(raw):
    source, dataset, _, _, bursts, rows = raw
    changed = []
    for row in rows:
        row = row.copy()
        if row['equipment_id'] == 'test' or row['cycle_index'] in (1, 8):
            values = bursts[row['equipment_id']][row['cycle_index']-1] + 10000
            path = source.root / row['equipment_id'] / f"{row['cycle_index']}.csv"
            np.savetxt(path, values, delimiter=',', header='horizontal,vertical', comments='', fmt='%.17g')
            row.update(extractVibration(values))
        changed.append(row)
    histories = {id: [{'path': record.path, 'sha256': hashlib.sha256((source.root/record.path).read_bytes()).hexdigest()}
        for record in records] for id, records in source.recordings.items()}
    modified = datasetFor(changed)
    after = RawVibrationSource.prepare(source.root, histories, modified, samplesPerRecording=32)
    assert after.scale(['train'], modified) == source.scale(['train'], dataset)
    with pytest.raises(ValueError, match='training'):
        source.scale([], dataset)


def test_compounds_are_atomic_and_order_independent(raw):
    first, second = case().components[0], case('vertical', kind='stuck', duration='transient', length=2).components[0]
    scenario = FaultCase(components=[first, second])
    result = apply(raw, scenario)
    reverse = apply(raw, FaultCase(components=[second, first]))
    assert result.applied and len(result.components) == 2
    np.testing.assert_array_equal(result.values, reverse.values)
    invalid = FaultCase(components=[first, case('unknown').components[0]])
    rejected = apply(raw, invalid)
    assert not rejected.applied and rejected.values is None and not rejected.components


def test_seed_zero_is_deterministic_and_transient_span_recovers(raw):
    scenario = case(onset_before_failure=None, seed=0, duration='transient', length=2)
    first, second = apply(raw, scenario), apply(raw, scenario)
    assert first.components == second.components
    np.testing.assert_array_equal(first.values, second.values)
    onset = first.components[0].onset_index
    assert onset == int(np.random.default_rng(0).integers(3, 8))
    clean = raw[1].sensor_matrix('test')
    np.testing.assert_array_equal(first.values[:onset], clean[:onset])
    np.testing.assert_array_equal(first.values[onset+2:], clean[onset+2:])


def test_raw_identity_survives_derived_feature_changes_and_root_moves(raw, tmp_path):
    import shutil
    source, _, _, histories, _, rows = raw
    rms = datasetFor(rows, ['horizontal_rms', 'vertical_rms'])
    narrowed = RawVibrationSource.prepare(source.root, histories, rms, samplesPerRecording=32)
    assert narrowed.historyIds == source.historyIds and narrowed.fingerprint != source.fingerprint
    copied = tmp_path / 'copy'
    copied.mkdir()
    for id in histories:
        shutil.copytree(source.root/id, copied/id)
    moved = RawVibrationSource.prepare(copied, histories, raw[1], samplesPerRecording=32)
    assert moved.fingerprint == source.fingerprint


def test_renaming_equipment_does_not_make_its_raw_history_fresh(raw):
    source, _, _, histories, _, rows = raw
    renamedRows = [dict(row, equipment_id='renamed-'+row['equipment_id']) for row in rows]
    renamedHistories = {'renamed-'+id: records for id, records in histories.items()}
    renamed = RawVibrationSource.prepare(source.root, renamedHistories, datasetFor(renamedRows), samplesPerRecording=32)
    assert renamed.historyIds['renamed-train'] == source.historyIds['train']
    assert renamed.historyIds['renamed-test'] == source.historyIds['test']


def test_validate_uses_bound_values_without_raw_reads_and_rejects_transforms(raw, monkeypatch):
    source, dataset, _, histories, _, rows = raw
    monkeypatch.setattr(source, '_read', lambda *args, **kwargs: pytest.fail('validate must not read recordings'))
    source.validate(dataset)
    transformed = [dict(row, horizontal_rms=row['horizontal_rms']/2) for row in rows]
    with pytest.raises(ValueError, match='feature'):
        source.validate(datasetFor(transformed))
    with pytest.raises(ValueError, match='feature'):
        RawVibrationSource.prepare(source.root, histories, datasetFor(transformed), samplesPerRecording=32)


def test_feature_projection_reuses_verified_record_metadata_without_io(raw, monkeypatch):
    source, dataset, _, _, _, rows = raw
    monkeypatch.setattr(RawVibrationSource, '_read', lambda *args, **kwargs: pytest.fail('projection must not read recordings'))
    rms = source.forDataset(datasetFor(rows, ['horizontal_rms', 'vertical_rms']))
    restored = rms.forDataset(dataset)
    assert rms.historyIds == source.historyIds
    assert restored.fingerprint == source.fingerprint and rms.fingerprint != source.fingerprint
    assert rms.featureNames == ('horizontal_rms', 'vertical_rms')
    with pytest.raises(ValueError, match='feature'):
        source.forDataset(datasetFor([dict(row, horizontal_rms=row['horizontal_rms']/2) for row in rows]))


@pytest.mark.parametrize('malformed', ['wrong_samples', 'nonfinite', 'missing_axis', 'incomplete_target'])
def test_invalid_signal_shape_finiteness_and_failure_mapping_are_rejected(raw, malformed):
    import copy
    source, dataset, _, histories, *_ = raw
    histories = copy.deepcopy(histories)
    path = source.root / histories['train'][0]['path']
    if malformed == 'wrong_samples':
        samples = np.ones((31, 2))
    elif malformed == 'nonfinite':
        samples = np.full((32, 2), np.nan)
    elif malformed == 'missing_axis':
        samples = np.ones((32, 1))
    else:
        dataset.frame.loc[dataset.frame.equipment_id == 'train', 'failure_cycle'] += 1
        samples = None
    if samples is not None:
        np.savetxt(path, samples, delimiter=',', header='horizontal,vertical', comments='', fmt='%.17g')
        histories['train'][0]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        RawVibrationSource.prepare(source.root, histories, dataset, samplesPerRecording=32)


def test_scale_cannot_include_the_failure_target_even_with_changed_config(raw):
    source, dataset, *_ = raw
    dataset.config = replace(CONFIG, exclude_failure_cycle=False)
    with pytest.raises(ValueError, match='failure target'):
        source.scale(['train'], dataset)


def test_verify_checks_original_files_without_signal_extraction(raw, monkeypatch):
    import app.faults.vibration as module
    monkeypatch.setattr(module, 'extractVibration', lambda *args: pytest.fail('verify must not extract signals'))
    raw[0].verify()


def test_changed_raw_files_reject_apply_and_verify(raw):
    source, _, _, histories, *_ = raw
    path = source.root / histories['test'][3]['path']
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='checksum'):
        apply(raw, case())
    with pytest.raises(ValueError, match='checksum'):
        source.verify()


@pytest.mark.parametrize('change', ['outside', 'duplicate', 'missing', 'hash', 'shape', 'unknown_feature'])
def test_source_admission_rejects_wrong_mapping_and_source(raw, tmp_path, change):
    import copy
    source, dataset, _, histories, *_ = raw
    histories = copy.deepcopy(histories)
    if change == 'outside':
        histories['test'][0]['path'] = '../outside.csv'
    elif change == 'duplicate':
        histories['test'][0] = histories['train'][0]
    elif change == 'missing':
        del histories['test']
    elif change == 'hash':
        histories['test'][0]['sha256'] = '0'*64
    elif change == 'shape':
        histories['test'].pop()
    else:
        dataset = datasetFor(raw[-1], ['horizontal_rms', 'vertical_rms'])
        dataset.mapping.sensors[0] = 'startup_relative_rms'
        dataset.frame.rename(columns={'horizontal_rms': 'startup_relative_rms'}, inplace=True)
    with pytest.raises(ValueError):
        RawVibrationSource.prepare(source.root, histories, dataset, samplesPerRecording=32)


def test_no_training_variation_and_unreachable_onsets_are_not_applicable(raw):
    source, dataset, builder, *_ = raw
    rul = dataset.frame[dataset.frame.equipment_id == 'test'].rul.to_numpy()
    result = source.apply('test', rul, case(kind='drift', severity_sd=1., sign=1, ramp_cycles=2), builder, CONFIG,
        rawScale={'horizontal': 0., 'vertical': 1.})
    assert not result.applied and result.values is None
    assert not apply(raw, case(onset_before_failure=20)).applied


def test_cooperative_checks_stop_before_more_io_and_future_bursts_do_not_change_prefix(raw):
    checks = []
    def stop():
        checks.append(1)
        if len(checks) == 2:
            raise RuntimeError('stopped')
    with pytest.raises(RuntimeError, match='stopped'):
        apply(raw, case(), check=stop)
    result = apply(raw, case())
    np.testing.assert_array_equal(result.values[:3], raw[1].sensor_matrix('test')[:3])


def test_unseen_future_burst_values_cannot_change_earlier_faulted_features(raw):
    import copy
    source, dataset, builder, histories, bursts, rows = raw
    before = apply(raw, case(kind='stuck'))
    path = source.root / histories['test'][6]['path']
    values = bursts['test'][6] * 100
    np.savetxt(path, values, delimiter=',', header='horizontal,vertical', comments='', fmt='%.17g')
    changed = copy.deepcopy(histories)
    changed['test'][6]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    changedRows = [dict(row, **extractVibration(values)) if row['equipment_id'] == 'test' and row['cycle_index'] == 7 else row for row in rows]
    changedDataset = datasetFor(changedRows)
    after = RawVibrationSource.prepare(source.root, changed, changedDataset, samplesPerRecording=32)
    result = after.apply('test', np.arange(7, -1, -1), case(kind='stuck'), builder, CONFIG, rawScale=source.scale(['train'], dataset))
    np.testing.assert_array_equal(result.values[:6], before.values[:6])
