"""Fixed RMS/rich-feature and LR/XGBoost comparison on development bearings."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))

import numpy as np
import pandas as pd

from app.config import ExperimentConfig
from app.data.contract import build_dataset
from app.experiments.provenance import source_digest
from app.experiments.validation import dependency_versions
from app.features.vibration import extractVibration, featureSchema
from app.models.candidates import LogisticRegressionCandidate, XGBoostCandidate
from app.schemas import ColumnMapping, SplitAssignment
from scripts import diagnose_clean_alarms as diagnostics
from scripts import evaluate_bearing_cap as capped


def readJson(path):
    return json.loads(path.read_text(encoding='utf-8'))


def writeJson(path, value):
    pending = path.with_suffix('.pending.json')
    pending.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    pending.replace(path)


def fileHash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extractBearing(source, id, recordings, *, expectedSamples=32768, expectedSources=None):
    if not re.fullmatch(r'Bearing[1-3]_[1-4]', id):
        raise ValueError('Only the twelve declared development bearings can be extracted')
    source = source.resolve()
    directories = list(source.glob(f'*/{id}'))
    if len(directories) != 1:
        raise ValueError(f'Expected one source directory for {id}')
    files = sorted(directories[0].glob('*.csv'), key=lambda path: int(path.stem))
    if [int(path.stem) for path in files] != list(range(1, recordings+1)):
        raise ValueError(f'Expected consecutive complete recordings for {id}')
    rows, manifest = [], []
    for index, path in enumerate(files, 1):
        relative = path.resolve().relative_to(source).as_posix()
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expectedSources is not None and expectedSources.get(relative) != digest:
            raise ValueError(f'Source checksum differs for {relative}')
        values = np.loadtxt(io.BytesIO(raw), delimiter=',', skiprows=1)
        if values.shape != (expectedSamples, 2):
            raise ValueError(f'Expected {expectedSamples} two-axis samples in {relative}')
        rows.append({'equipment_id': id, 'cycle_index': index, **extractVibration(values)})
        manifest.append({'path': relative, 'sha256': digest})
        if index % 250 == 0:
            print(f'{id}: {index}/{recordings} recordings', flush=True)
    print(f'{id}: {recordings} complete', flush=True)
    return pd.DataFrame(rows), manifest


def saveBearing(directory, id, frame, sources):
    csv = directory / f'{id}.csv'
    pending = csv.with_suffix('.pending.csv')
    frame.to_csv(pending, index=False, float_format='%.17g')
    pending.replace(csv)
    writeJson(directory / f'{id}.json', {'csv_sha256': fileHash(csv), 'rows': len(frame), 'sources': sources})


def loadBearing(directory, id):
    csv = directory / f'{id}.csv'
    manifest = readJson(directory / f'{id}.json')
    if fileHash(csv) != manifest['csv_sha256']:
        raise ValueError(f'Feature checksum differs for {id}')
    frame = pd.read_csv(csv)
    if len(frame) != manifest['rows'] or set(frame.equipment_id) != {id}:
        raise ValueError(f'Feature identity differs for {id}')
    return frame


def makeDataset(frame, sensors, config):
    mapping = ColumnMapping(equipment_id='equipment_id', cycle_index='cycle_index', sensors=sensors, failure_cycle=None, inferred=False)
    return build_dataset(frame[['equipment_id', 'cycle_index', *sensors]], mapping, dataset_id='xjtu-sy-fixed-vibration-v1',
        source='Measured laboratory vibration features; acquisition minutes, complete histories', config=config)


def writeReport(results, path):
    lines = ['# Fixed vibration-feature experiment', '',
        'Twelve previously examined development bearings only; no independent validation, reserved signal parsing or model promotion.', '',
        '| Input/model | Useful warnings | Pooled alarm time | Worst bearing | Pooled limits met | Per-bearing qualifying folds |',
        '|---|---:|---:|---:|---|---:|']
    for name, result in results.items():
        pooled, strict = result['pooled'], result['per_bearing']
        metrics = pooled['metrics']
        lines.append(f"| {name} | {metrics['detected']}/{metrics['engines']} | {metrics['early_alarm_burden']:.2%} | {pooled['equipment_max_burden']:.2%} | {pooled['clean_limits_met']} | {strict['qualified_folds']}/{strict['total_folds']} |")
    lines.extend(['', 'The fixed feature pack contains RMS, population Pearson kurtosis, crest factor, peak-to-peak amplitude and three mean-centered one-sided spectral energies per accelerometer: [0,1000), [1000,5000), and [5000,12800] Hz. Constants have zero kurtosis; zero recordings have zero crest factor. Broad bands are prototype features, not validated bearing-fault frequencies.', '',
        'All models use the original grouped outer splits and operating windows, 80% useful-warning target and 5% alarm budget. LR uses C=1 and max_iter=300. XGBoost uses its existing depth4/300-tree settings with fixed seed20261031 and one CPU thread. There is no post-result feature or hyperparameter search.', '',
        'Pooled results are nested development diagnostics under the existing pooled threshold selector. The separate per-bearing selector uses exact inner-score cutoffs and rejects insufficient warnings or missing early windows; rejected groups are not scored as fallbacks. Its partial or absent outer results must not be confused with the full pooled diagnostic.', '',
        'Each inner model has four training bearings in this small design. Input shape/frequency features are computed from the current completed recording only; imputation/scaler/model/threshold fitting stays inside outer training groups. Raw acceleration files are hash-checked against the earlier development-source manifest. RMS is cross-checked against the previous development CSV.', '',
        'The data are accelerated laboratory signals sampled in 1.28-second bursts once per minute. Startup is not certified healthy; windows and bands remain provisional pending engineer review. Every original bearing remains exposed. Raw-channel fault tests and a new cohort are required before a changed procedure can support an independent robustness claim.'])
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-root', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True, help='Earlier development RMS CSV.')
    parser.add_argument('--source-manifest', type=Path, required=True, help='Earlier development raw-file hashes.')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume', action='store_true', help='Reuse only matching completed feature/arm checkpoints.')
    args = parser.parse_args(argv)
    protocol, baseline = readJson(args.protocol), readJson(args.baseline)
    ids = protocol['development']
    if len(ids) != 12 or len(set(ids)) != 12 or any(not re.fullmatch(r'Bearing[1-3]_[1-4]', id) for id in ids):
        raise ValueError('The experiment requires exactly the twelve original development bearings')
    if set(ids) & set(protocol['reserved']) or protocol['samples_per_recording'] != 32768 or protocol['sampling_hz'] != 25600:
        raise ValueError('Source identity or sampling protocol differs')
    config = ExperimentConfig(**baseline['config'])
    folds = [row['evaluation_ids'] for row in baseline['variants']['raw_rms']['folds']]
    sources = {row['path'].replace('\\', '/'): row['sha256'] for row in readJson(args.source_manifest)['files']}
    inputs = [args.protocol, args.baseline, args.reference, args.source_manifest]
    code = [Path(__file__), ROOT / 'backend/app/features/vibration.py', Path(diagnostics.__file__), Path(capped.__file__)]
    frozen = {'version': 1, 'development': ids, 'reserved_not_read': protocol['reserved'], 'features': featureSchema(),
        'config': config.as_dict(), 'folds': folds, 'arms': ['rms_lr', 'rich_lr', 'rms_xgb', 'rich_xgb'],
        'backend_source': source_digest(), 'dependencies': dependency_versions(),
        'lr': {'C': 1., 'max_iter': 300}, 'xgb': {'max_depth': 4, 'n_estimators': 300, 'model_seed': 20261031, 'n_jobs': 1},
        'inputs': {str(path): fileHash(path) for path in inputs}, 'code': {str(path): fileHash(path) for path in code},
        'raw_fault_tests_completed': False, 'independent_validation': False}
    if args.resume:
        if readJson(args.output / 'protocol.json') != frozen:
            raise ValueError('Resume requires the exact frozen code, inputs and experiment settings')
    else:
        args.output.mkdir(parents=True, exist_ok=False)
        writeJson(args.output / 'protocol.json', frozen)
    directory = args.output / 'bearings'
    directory.mkdir(exist_ok=True)
    pending = [id for id in ids if not (directory / f'{id}.json').exists()]
    with ThreadPoolExecutor(max_workers=4) as workers:
        tasks = {workers.submit(extractBearing, args.raw_root, id, protocol['recordings'][id], expectedSources=sources): id for id in pending}
        for task in as_completed(tasks):
            frame, manifest = task.result()
            saveBearing(directory, tasks[task], frame, manifest)
    frame = pd.concat([loadBearing(directory, id) for id in ids], ignore_index=True).sort_values(['equipment_id', 'cycle_index'])
    reference = pd.read_csv(args.reference)
    if set(reference.equipment_id) != set(ids) or len(reference) != len(frame):
        raise ValueError('Reference histories do not match the development features')
    matched = frame.merge(reference, on=['equipment_id', 'cycle_index'], suffixes=('', '_reference'), validate='one_to_one')
    if len(matched) != len(frame):
        raise ValueError('Reference recording identities differ')
    for sensor in ('horizontal_rms', 'vertical_rms'):
        np.testing.assert_allclose(matched[sensor], matched[sensor + '_reference'], rtol=1e-12, atol=1e-12)
    writeJson(args.output / 'feature-check.json', {'rows': len(frame), 'histories': ids, 'rms_matches_reference': True, 'reserved_signals_read': False})
    config = replace(config, holdout_engines=0)
    splits = SplitAssignment(holdout=[], development=ids, folds=folds, seed=config.base_seed, config_fingerprint=config.fingerprint())
    recipes = [('rms_lr', ['horizontal_rms', 'vertical_rms'], LogisticRegressionCandidate('bearing-lr', frozen['lr'])),
        ('rich_lr', list(featureSchema()), LogisticRegressionCandidate('bearing-lr', frozen['lr'])),
        ('rms_xgb', ['horizontal_rms', 'vertical_rms'], XGBoostCandidate('bearing-xgb', frozen['xgb'])),
        ('rich_xgb', list(featureSchema()), XGBoostCandidate('bearing-xgb', frozen['xgb']))]
    results = {}
    for name, sensors, candidate in recipes:
        path = args.output / f'{name}.json'
        checksum = args.output / f'{name}.sha256'
        if path.exists():
            if not checksum.exists() or fileHash(path) != checksum.read_text().strip():
                raise ValueError(f'Completed arm checksum differs for {name}')
            results[name] = readJson(path)
        else:
            print(f'Evaluating {name}', flush=True)
            dataset = makeDataset(frame, sensors, config)
            results[name] = {'features': sensors, 'params': candidate.params,
                'pooled': diagnostics.nestedClean(dataset, splits, candidate), 'per_bearing': capped.nestedCapped(dataset, splits, candidate)}
            writeJson(path, results[name])
            checksum.write_text(fileHash(path) + '\n', encoding='utf-8')
        writeReport(results, args.output / 'report.md')
    writeJson(args.output / 'results.json', results)
    print('All four frozen arms complete; no model promoted.', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
