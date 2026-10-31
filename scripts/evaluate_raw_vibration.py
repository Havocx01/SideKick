"""Fixed development diagnostics with faults applied before vibration feature extraction."""
import argparse
from dataclasses import replace
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))

import joblib
import pandas as pd

from app.config import ExperimentConfig
from app.experiments.provenance import source_digest
from app.experiments.validation import dependency_versions
from app.faults.evaluator import FaultEvaluation, FixedDevelopmentEvaluator
from app.faults.scenarios import FaultCase, FaultPolicy, fingerprint
from app.faults.vibration import RawVibrationSource
from app.investigator.findings import FindingCriterion, classify
from app.investigator.thresholds import assessThresholds
from app.models.candidates import LogisticRegressionCandidate, XGBoostCandidate
from app.models.train import train_development
from app.schemas import SplitAssignment
from scripts import evaluate_vibration_features as featureStudy
from scripts.evaluate_vibration_features import fileHash, loadBearing, makeDataset, readJson, writeJson


def cases():
    def atom(axis, kind, onset=30):
        value = {'sensor': axis, 'kind': kind, 'duration': 'persistent', 'onset_before_failure': onset}
        if kind == 'drift':
            value |= {'severity_sd': 1., 'sign': 1, 'ramp_cycles': 10}
        return value

    return [FaultCase(components=parts) for parts in [
        [atom('horizontal', 'dropout')], [atom('vertical', 'dropout')],
        [atom('horizontal', 'stuck')], [atom('vertical', 'stuck')],
        [atom('horizontal', 'dropout'), atom('vertical', 'dropout')],
        [atom('horizontal', 'stuck'), atom('vertical', 'stuck')],
        [atom('horizontal', 'drift', 60)],
        [atom('horizontal', 'drift', 60), atom('vertical', 'dropout', 60)]]]


def saveObject(path, value):
    pending = path.with_suffix('.pending.joblib')
    joblib.dump(value, pending, compress=3)
    pending.replace(path)
    path.with_suffix(path.suffix + '.sha256').write_text(fileHash(path) + '\n', encoding='utf-8')


def loadObject(path):
    if fileHash(path) != path.with_suffix(path.suffix + '.sha256').read_text().strip():
        raise ValueError('Local diagnostic checkpoint checksum differs')
    return joblib.load(path)


def evaluateCase(engine, case, path):
    if path.exists():
        saved = readJson(path)
        if fingerprint(saved['evaluation']) != saved['digest']:
            raise ValueError('Raw fault checkpoint checksum differs')
        result = FaultEvaluation.model_validate(saved['evaluation'])
        if (result.context_fingerprint != engine.context_fingerprint or result.policy_fingerprint != engine.policy.fingerprint
                or result.scenario != case or result.raw_source is None or result.raw_source['fingerprint'] != engine.rawSource.fingerprint):
            raise ValueError('Raw fault checkpoint belongs to a different fixed context')
        return result
    result = engine.evaluate(case)
    payload = result.model_dump(mode='json')
    writeJson(path, {'evaluation': payload, 'digest': fingerprint(payload)})
    return result


def checkSource(source, histories):
    actual = {id: [{'path': row.path, 'sha256': row.sha256} for row in rows] for id, rows in source.recordings.items()}
    if actual != histories or source.samplingHz != 25600 or source.samplesPerRecording != 32768:
        raise ValueError('Raw checkpoint differs from the declared recording manifest')


def loadTraining(path, metadata, dataset, splits, candidate):
    saved = loadObject(path)
    if not isinstance(saved, dict) or saved.get('metadata') != metadata or set(saved) != {'metadata', 'training'}:
        raise ValueError('Training checkpoint belongs to a different diagnostic arm or protocol')
    training = saved['training']
    if (training.config != dataset.config or training.splits != splits or training.dataset.mapping != dataset.mapping
            or not training.dataset.frame.equals(dataset.frame) or set(training.specs) != {candidate.name}
            or type(training.specs[candidate.name]) is not type(candidate) or training.specs[candidate.name].params != candidate.params
            or any(set(fold.candidates) != {candidate.name} or type(fold.candidates[candidate.name]) is not type(candidate)
                or fold.candidates[candidate.name].params != candidate.params for fold in training.folds)):
        raise ValueError('Training checkpoint differs from its declared model, data or folds')
    return training


def loadArm(path, metadata, engine, criterion, checks):
    if fileHash(path) != path.with_suffix(path.suffix + '.sha256').read_text().strip():
        raise ValueError('Completed diagnostic arm checksum differs')
    result = readJson(path)
    if (result.get('metadata') != metadata or result.get('context') != engine.context_fingerprint
            or result.get('source') != engine.rawSource.fingerprint or result.get('criterion') != criterion.model_dump(mode='json')
            or result.get('checks') != checks or len(result.get('evaluations', [])) != len(cases())):
        raise ValueError('Completed diagnostic arm differs from its fixed context or protocol')
    evaluations = [FaultEvaluation.model_validate(value) for value in result['evaluations']]
    for case, evaluation in zip(cases(), evaluations, strict=True):
        if (evaluation.scenario != case or evaluation.context_fingerprint != engine.context_fingerprint
                or evaluation.policy_fingerprint != engine.policy.fingerprint or evaluation.raw_source is None
                or evaluation.raw_source['fingerprint'] != engine.rawSource.fingerprint
                or [(row.candidate, row.threshold) for row in evaluation.models] != list(engine.thresholds.items())):
            raise ValueError('Completed raw evaluation differs from its declared scenario or model')
    if result.get('findings') != [classify(value, criterion).model_dump(mode='json') for value in evaluations]:
        raise ValueError('Completed raw findings differ from their recorded evaluations')
    return result


def freeze(features, output, resume):
    protocol = readJson(features / 'protocol.json')
    ids = protocol['development']
    if len(ids) != 12 or len(set(ids)) != 12 or any(not re.fullmatch(r'Bearing[1-3]_[1-4]', id) for id in ids):
        raise ValueError('Raw diagnostics require exactly the twelve original development bearings')
    if set(ids) & set(protocol['reserved_not_read']):
        raise ValueError('Development and previously exposed reserved bearings overlap')
    inputs = [features / 'protocol.json', features / 'feature-check.json']
    inputs += [features / 'bearings' / f'{id}.{suffix}' for id in ids for suffix in ('csv', 'json')]
    config = replace(ExperimentConfig(**protocol['config']), holdout_engines=0)
    frozen = {'version': 1, 'backend_source': source_digest(), 'script_sha256': fileHash(Path(__file__)),
        'helper_sha256': {str(Path(module.__file__).relative_to(ROOT)): fileHash(Path(module.__file__))
            for module in (featureStudy, featureStudy.diagnostics, featureStudy.capped)},
        'dependencies': dependency_versions(), 'inputs': {str(path): fileHash(path) for path in inputs},
        'development': ids, 'reserved_not_read': protocol['reserved_not_read'], 'config': config.as_dict(),
        'folds': protocol['folds'], 'lr': protocol['lr'], 'xgb': protocol['xgb'], 'threshold': .5,
        'cases': [case.model_dump(mode='json') for case in cases()],
        'measurement': 'Whole acquired accelerometer bursts; sample-and-hold, missing axis, or additive offset drift',
        'purpose': 'Fixed-cutoff development diagnostic, not nested performance estimation or model promotion',
        'independent_validation': False, 'requirements_confirmed': False,
        'startup_normalization': 'Unsupported; transformed input is rejected, not treated as raw-derived features'}
    if resume:
        if readJson(output / 'protocol.json') != frozen:
            raise ValueError('Resume requires the exact frozen source, inputs and settings')
    else:
        output.mkdir(parents=True, exist_ok=False)
        writeJson(output / 'protocol.json', frozen)
    return frozen


def report(results, path):
    lines = ['# Raw vibration development diagnostics', '',
        'Previously examined development bearings only. Fixed cutoff 0.5, unchanged warning/alarm limits. This is not independent validation or a nested model comparison.', '',
        '| Input/model | Clean useful warnings | Pooled early alarms | Worst machine | Missing early windows | Qualifying cutoff found (pooled / each machine) | Measured / inconclusive / other faults |',
        '|---|---:|---:|---:|---:|---|---|']
    for name, row in results.items():
        clean = row['checks']['per_equipment']['current']['clean']
        statuses = [finding['status'] for finding in row['findings']]
        measured, inconclusive = statuses.count('measured_failure'), statuses.count('inconclusive')
        checks = ' / '.join(row['checks'][scope]['status'] for scope in ('pooled', 'per_equipment'))
        missing = sum(item['exposure']['eligible_cycles'] == 0 for item in clean['equipment'])
        lines.append(f"| {name} | {clean['detection']:.2%} | {clean['alarmBurden']:.2%} | {clean['worstEquipmentBurden']:.2%} | {missing} | {checks} | {measured} / {inconclusive} / {len(statuses)-measured-inconclusive} |")
    lines += ['', 'Threshold searches are read-only diagnostics; no suggested threshold is applied. Findings use the declared 0.5 cutoff and per-equipment criterion. A failing clean gate is inconclusive evidence, not a discovered robustness failure.', '',
        'The source binding checks every burst hash and its clean extracted values. Both RMS and rich arms share raw history identities. Drift scale uses only scorable training-group samples. Dropout makes all affected-axis features missing; stuck holds the final sample of the prior burst; additive drift changes samples before feature extraction. These are prototype measurement faults, not mechanical damage or continuous sensor behavior between acquisitions.', '',
        'Onsets and ramps are acquisition-recording units (one minute for this dataset). The 60-recording cases exclude short histories explicitly; missing early-life windows never become zero-alarm passes. Startup-normalized inputs, partial-burst corruption, raw remote jobs and raw augmentation remedies are not supported. No reserved signals, new equipment, paid APIs or real engineer review were used.']
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--features', type=Path, required=True)
    parser.add_argument('--raw-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume', action='store_true', help='Trust and reuse matching locally generated Python checkpoints.')
    args = parser.parse_args(argv)
    frozen = freeze(args.features, args.output, args.resume)
    config = ExperimentConfig(**frozen['config'])
    frame = pd.concat([loadBearing(args.features / 'bearings', id) for id in frozen['development']], ignore_index=True)
    sensors = [name for name in frame.columns if name not in ('equipment_id', 'cycle_index')]
    rich = makeDataset(frame, sensors, config)
    sourcePath = args.output / 'raw-source.joblib'
    histories = {id: readJson(args.features / 'bearings' / f'{id}.json')['sources'] for id in frozen['development']}
    if args.resume and sourcePath.exists():
        source = loadObject(sourcePath)
        if type(source) is not RawVibrationSource:
            raise ValueError('Unsupported local raw-source checkpoint')
        source.root = args.raw_root.resolve()
        checkSource(source, histories)
        source.validate(rich)
        source.verify()
    else:
        print('Verifying and extracting the declared development recordings', flush=True)
        source = RawVibrationSource.prepare(args.raw_root, histories, rich)
        saveObject(sourcePath, source)
    writeJson(args.output / 'source-check.json', {'fingerprint': source.fingerprint, 'histories': source.historyIds,
        'recordings': len(frame), 'reserved_signals_read': False})
    splits = SplitAssignment(holdout=[], development=frozen['development'], folds=frozen['folds'], seed=config.base_seed,
        config_fingerprint=config.fingerprint())
    policy = FaultPolicy(allowed_sensors=('horizontal', 'vertical'), max_seconds=300,
        assumptions='Raw-axis measurement corruptions on completed vibration recordings; acquisition gaps and mechanical damage are not simulated.')
    results = {}
    for name in ('rms_lr', 'rich_lr', 'rms_xgb', 'rich_xgb'):
        path = args.output / f'{name}.json'
        columns = sensors if name.startswith('rich') else ['horizontal_rms', 'vertical_rms']
        dataset = makeDataset(frame, columns, config)
        bound = source.forDataset(dataset)
        trainingPath = args.output / f'{name}.joblib'
        candidate = (LogisticRegressionCandidate('raw-lr', frozen['lr']) if name.endswith('lr')
            else XGBoostCandidate('raw-xgb', frozen['xgb']))
        metadata = {'arm': name, 'protocol': fingerprint(frozen), 'source': bound.fingerprint}
        if args.resume and trainingPath.exists():
            training = loadTraining(trainingPath, metadata, dataset, splits, candidate)
        else:
            if path.exists():
                raise ValueError('Completed diagnostic arm is missing its original fitted checkpoint')
            print(f'Fitting fixed {name} development models', flush=True)
            training = train_development(dataset, config=config, splits=splits, candidates=[candidate])
            saveObject(trainingPath, {'metadata': metadata, 'training': training})
        candidate = next(iter(training.specs))
        engine = FixedDevelopmentEvaluator(training, {candidate: frozen['threshold']}, policy, rawSource=bound)
        scores = training.out_of_fold[candidate]
        checks = {scope: assessThresholds(scores, frozen['threshold'], FindingCriterion(version=2, candidate=candidate, alarm_scope=scope),
            config, engine.context_fingerprint, maxSeconds=300).model_dump(mode='json') for scope in ('pooled', 'per_equipment')}
        criterion = FindingCriterion(version=2, candidate=candidate, alarm_scope='per_equipment')
        if path.exists():
            results[name] = loadArm(path, metadata, engine, criterion, checks)
            continue
        evaluations, findings = [], []
        caseDirectory = args.output / name
        caseDirectory.mkdir(exist_ok=True)
        for case in cases():
            print(f'{name}: {case.scenario_id}', flush=True)
            result = evaluateCase(engine, case, caseDirectory / f'{case.scenario_id}.json')
            evaluations.append(result.model_dump(mode='json'))
            findings.append(classify(result, criterion).model_dump(mode='json'))
        results[name] = {'metadata': metadata, 'context': engine.context_fingerprint, 'source': bound.fingerprint, 'checks': checks,
            'criterion': criterion.model_dump(mode='json'), 'evaluations': evaluations, 'findings': findings}
        writeJson(path, results[name])
        path.with_suffix(path.suffix + '.sha256').write_text(fileHash(path) + '\n', encoding='utf-8')
        report(results, args.output / 'report.md')
    writeJson(args.output / 'results.json', results)
    report(results, args.output / 'report.md')
    print('All four raw measurement diagnostic arms complete; no model or threshold promoted.', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
