"""Select thresholds with a per-bearing alarm cap, using development data only."""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))

import numpy as np

from app.faults.replay import load_trusted_context
from app.models.candidates import LogisticRegressionCandidate
from app.models.splits import validate_splits
from app.models.train import fit_final, train_development
from app.schemas import SplitAssignment
from app.scoring.metrics import aggregate, score_engine
from app.scoring.selection import default_criteria
from scripts import diagnose_clean_alarms as diagnostics
from scripts import evaluate_equipment_balance as balanced


def calibrationAt(perEngine, threshold, config):
    scorings, equipment = [], []
    for id, row in sorted(perEngine.items()):
        scoring = score_engine(id, row.scores, row.cycles, row.rul, threshold, config=config)
        scorings.append(scoring)
        equipment.append(diagnostics.equipmentSummary(scoring, row.scores, row.rul, config))
    return diagnostics.cleanSummary(scorings, equipment, config)


def chooseCapped(perEngine, config):
    if not perEngine:
        raise ValueError('Cannot select a threshold from empty calibration histories')
    scores = np.concatenate([row.scores for row in perEngine.values()])
    values = np.unique(scores[np.isfinite(scores)])
    if not len(values):
        raise ValueError('Calibration histories contain no finite scores')
    thresholds = np.append(values, np.nextafter(values[-1], np.inf))
    cache = {}

    def evaluate(index):
        if index not in cache:
            cache[index] = calibrationAt(perEngine, float(thresholds[index]), config)
        return cache[index]

    first = evaluate(0)
    if first['equipment_max_burden'] is None:
        return {'qualified': False, 'threshold': None, 'selected': None, 'best_capped': None, 'diagnostic_threshold': None,
            'missing_early_windows': first['equipment_without_early_window'], 'reasons': ['no_eligible_early_window'],
            'candidate_count': len(thresholds), 'evaluated_thresholds': len(cache)}

    # Higher cutoffs can only remove active alarms under the fixed episode rules.
    low, high = 0, len(thresholds)-1
    while low < high:
        middle = (low+high) // 2
        if evaluate(middle)['equipment_max_burden'] <= config.max_early_alarm_burden:
            high = middle
        else:
            low = middle+1
    maximumWarnings = evaluate(low)['metrics']['detected']
    high = len(thresholds)-1
    while low < high:
        middle = (low+high+1) // 2
        if evaluate(middle)['metrics']['detected'] == maximumWarnings:
            low = middle
        else:
            high = middle-1
    best = evaluate(low)
    reasons = []
    if best['metrics']['detection_fraction'] < config.min_detection_fraction:
        reasons.append('warning_requirement_not_met')
    if best['equipment_without_early_window']:
        reasons.append('missing_early_window_coverage')
    qualified = not reasons
    return {'qualified': qualified, 'threshold': float(thresholds[low]) if qualified else None,
        'selected': best if qualified else None, 'best_capped': best, 'diagnostic_threshold': float(thresholds[low]),
        'missing_early_windows': best['equipment_without_early_window'], 'reasons': reasons,
        'candidate_count': len(thresholds), 'evaluated_thresholds': len(cache)}


def nestedCapped(dataset, splits, candidate):
    validate_splits(splits)
    if len(splits.folds) < 3:
        raise ValueError('Nested threshold selection needs at least three outer folds')
    if set(dataset.equipment_ids) != set(splits.development):
        raise ValueError('Threshold study accepts only the development subset')
    scorings, equipment, folds = [], [], []
    for index, evaluationIds in enumerate(splits.folds):
        innerFolds = [list(ids) for other, ids in enumerate(splits.folds) if other != index]
        trainingIds = [id for ids in innerFolds for id in ids]
        config = replace(dataset.config, n_folds=len(innerFolds), holdout_engines=0)
        trainingData = replace(dataset.subset(trainingIds), config=config)
        inner = SplitAssignment(holdout=[], development=trainingIds, folds=innerFolds, seed=splits.seed, config_fingerprint=config.fingerprint())
        training = train_development(trainingData, config=config, candidates=[candidate], splits=inner)
        choice = chooseCapped(training.out_of_fold[candidate.name], config)
        fold = {'fold': index, 'threshold_ids': trainingIds, 'evaluation_ids': list(evaluationIds), 'choice': choice, 'evaluation': None}
        if choice['qualified']:
            model, builder, _ = fit_final(trainingData, inner, candidate, config=config)
            current, rows = diagnostics.scoreDesign(model, builder, dataset.subset(evaluationIds), choice['threshold'])
            scorings.extend(current)
            equipment.extend(rows)
            fold['evaluation'] = aggregate(current, config=config).model_dump(mode='json')
        folds.append(fold)
    summary = diagnostics.cleanSummary(scorings, equipment, dataset.config) if scorings else None
    complete = len(equipment) == len(splits.development)
    passed = bool(summary and complete and summary['clean_limits_met'] and not summary['equipment_above_budget']
        and not summary['equipment_without_early_window'])
    return {'expected_histories': len(splits.development), 'evaluated_histories': len(equipment),
        'qualified_folds': sum(fold['choice']['qualified'] for fold in folds), 'total_folds': len(folds), 'complete_evaluation': complete,
        'metrics': summary['metrics'] if summary else None, 'equipment': equipment, 'outer_summary': summary,
        'development_procedure_passed': passed, 'folds': folds}


def study(training):
    names = [name for name, candidate in training.specs.items() if isinstance(candidate, LogisticRegressionCandidate)]
    if len(names) != 1:
        raise ValueError('Select a context containing exactly one logistic-regression candidate')
    source = training.specs[names[0]]
    development = training.dataset.subset(training.splits.development)
    relative = diagnostics.relativeRms(development, training.config.feature_window)
    recipes = [(development, LogisticRegressionCandidate), (development, balanced.EquipmentBalancedLR),
        (relative, LogisticRegressionCandidate), (relative, balanced.EquipmentBalancedLR)]
    variants = {label: nestedCapped(dataset, training.splits, kind(source.config_id, source.params))
        for label, (dataset, kind) in zip(balanced.VARIANTS, recipes, strict=True)}
    return {'development_ids': development.equipment_ids, 'reserved_scored': False, 'independent_validation': False,
        'config': training.config.as_dict(), 'candidate': source.name, 'source_params': source.params, 'variants': variants,
        'limitations': ['Exploratory reuse of the same development equipment, not an independent validation cohort.',
            'Only inner grouped OOF scores select cutoffs; outer groups never supply calibration evidence.',
            'Missing early-window coverage prevents admitting a threshold; such histories are not zero-alarm passes.',
            'Best capped choices below the warning target are diagnostic only and are never applied as fallbacks.',
            'Exact score breakpoints differ from the earlier pooled 40-quantile selector in resolution and objective.',
            'An infeasibility result applies to these recorded inner scores and fixed episode rules, not every possible model.',
            'Partial outer evaluations are conditional on successful calibration and must not be presented as twelve-bearing results.',
            'Relative RMS uses causal per-bearing startup readings, which are not certified healthy.',
            'Raw-telemetry fault tests, engineer review and a fresh independent cohort are still needed before promotion.',
            'No saved model, threshold, original protocol, exposure record or application default was replaced.']}


def writeReport(result, path):
    lines = ['# Per-bearing threshold-cap experiment', '',
        'Development data only. The warning requirement and all warning/episode windows remain fixed. No model was promoted.', '',
        '| Variant | Qualified inner folds | Outer histories scored | Useful outer warnings | Complete procedure passed |', '|---|---:|---:|---:|---|']
    for label, row in result['variants'].items():
        warnings = f"{row['metrics']['detected']}/{row['metrics']['engines']}" if row['metrics'] else 'Not evaluated'
        lines.append(f"| {label} | {row['qualified_folds']}/{row['total_folds']} | {row['evaluated_histories']}/{row['expected_histories']} | {warnings} | {row['development_procedure_passed']} |")
    lines.extend(['', '## Inner calibration results', '',
        'The maximum warning count below is attainable under the per-bearing cap on assessable inner histories. It is not an outer evaluation or an admitted threshold when coverage is missing. Rejected choices are never applied to outer equipment.', '',
        '| Variant | Fold | Best capped warnings | Worst capped alarm time | Missing early windows | Rejection reasons |', '|---|---:|---:|---:|---|---|'])
    for label, row in result['variants'].items():
        for fold in row['folds']:
            choice, best = fold['choice'], fold['choice']['best_capped']
            warnings = f"{best['metrics']['detected']}/{best['metrics']['engines']}" if best else 'Unavailable'
            burden = f"{best['equipment_max_burden']:.2%}" if best else 'Unavailable'
            lines.append(f"| {label} | {fold['fold']} | {warnings} | {burden} | {', '.join(choice['missing_early_windows']) or 'None'} | {', '.join(choice['reasons']) or 'None'} |")
    lines.extend(['', '## Method', '',
        'For each outer group, train inner grouped models on the other development histories. Search every distinct finite inner-OOF score breakpoint plus an above-maximum never-alert cutoff. With fixed episode rules, higher cutoffs cannot increase active-alarm time or useful-warning count. Binary search first finds the per-bearing-cap boundary, then the highest threshold preserving its maximum warning count. This tie-break weakly minimizes all alarm burdens at that warning count.', '',
        'Admit a threshold only if the recorded useful-warning requirement, per-bearing cap and complete early-window coverage all hold. Otherwise retain its best capped result for diagnosis and skip outer model refit/scoring. All bearings remain in the warning denominator. A missing alarm window is not silently excluded from qualification.', '',
        'Weights, imputation, scaler parameters, model coefficients and selected thresholds use outer training equipment only. The relative reference uses each bearing\'s own current/past startup observations and then freezes. C/max_iter and all operational windows match the earlier four-arm study.', '',
        'No admission is different from a zero-alarm success. Partial outer results, if any, describe only the scored subset and are not evidence on all twelve histories. The old fifteen-bearing cohort remains exposed; any changed procedure needs new equipment for an independent validation claim.', '',
        '## Limits', '', *['- ' + item for item in result['limitations']]])
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context', required=True, type=Path, help='Existing local fitted development package.')
    parser.add_argument('--trust-local-artifact', action='store_true', help='Only for a package you produced and trust; joblib can execute code.')
    parser.add_argument('--output', required=True, type=Path, help='New output directory; existing results are never replaced.')
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False)
    evaluator = load_trusted_context(args.context, trusted=args.trust_local_artifact)
    training = evaluator.snapshot()
    paths = [Path(__file__), Path(diagnostics.__file__), Path(balanced.__file__)]
    protocol = {'context': evaluator.context_fingerprint, 'development_ids': training.splits.development, 'outer_folds': training.splits.folds,
        'variants': balanced.VARIANTS, 'criteria': default_criteria(training.config).model_dump(mode='json'),
        'threshold_rule': 'Exact inner-OOF score breakpoints; maximize warnings under each bearing alarm cap, then take the highest cutoff retaining that count.',
        'rejection': 'No threshold or outer refit/scoring if warning requirement or complete early-window coverage fails; diagnostics are not fallbacks.',
        'reserved_scored': False, 'independent_validation': False,
        'source_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}}
    (args.output / 'protocol.json').write_text(json.dumps(protocol, indent=2) + '\n', encoding='utf-8')
    for source in paths:
        (args.output / source.name).write_bytes(source.read_bytes())
    result = study(training)
    (args.output / 'results.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    writeReport(result, args.output / 'report.md')
    print(json.dumps({label: {'qualified_folds': row['qualified_folds'], 'evaluated_histories': row['evaluated_histories'],
        'development_procedure_passed': row['development_procedure_passed']} for label, row in result['variants'].items()}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
