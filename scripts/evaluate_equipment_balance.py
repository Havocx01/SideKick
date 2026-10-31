"""Test equipment-balanced logistic regression on development bearings only."""
import argparse
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
from app.scoring.selection import default_criteria
from scripts import diagnose_clean_alarms as diagnostics

VARIANTS = ('raw_rms', 'raw_equipment_balanced', 'relative_rms', 'relative_equipment_balanced')
WEIGHTING = ('Equal total weight per training equipment; split equally across its observed classes, then equally across rows in each class. '
    'Weights have mean one. Both scaling and logistic regression use them, with no additional automatic class weighting. '
    'A one-class history retains its full equipment weight in that class; global class balance is then not guaranteed.')


def equipmentWeights(data):
    if not len(data):
        raise ValueError('Cannot weight an empty training design')
    if not np.isin(data.y, [0, 1]).all():
        raise ValueError('Equipment balancing needs binary labels')
    equipment = np.unique(data.equipment_id)
    weights = np.empty(len(data), dtype=float)
    for id in equipment:
        members = data.equipment_id == id
        classes = np.unique(data.y[members])
        for label in classes:
            rows = members & (data.y == label)
            weights[rows] = len(data) / (len(equipment) * len(classes) * int(rows.sum()))
    return weights


class EquipmentBalancedLR(LogisticRegressionCandidate):
    def describe(self):
        return f"Equipment/class-balanced logistic regression, C={self.params.get('C', 1.0)}"

    def fit(self, train, *, augmented=None):
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        train.assert_finite()
        weights = equipmentWeights(train)
        self._pipeline = Pipeline([('scale', StandardScaler()), ('model', LogisticRegression(
            C=float(self.params.get('C', 1.0)), max_iter=int(self.params.get('max_iter', 2000)), class_weight=None, solver='lbfgs'))])
        self._pipeline.fit(train.X, train.y, scale__sample_weight=weights, model__sample_weight=weights)
        self._feature_names = list(train.feature_names)
        self._fitted = True


def study(training):
    names = [name for name, candidate in training.specs.items() if isinstance(candidate, LogisticRegressionCandidate)]
    if len(names) != 1:
        raise ValueError('Select a context containing exactly one logistic-regression candidate')
    source = training.specs[names[0]]
    development = training.dataset.subset(training.splits.development)
    relative = diagnostics.relativeRms(development, training.config.feature_window)
    recipes = [(development, LogisticRegressionCandidate), (development, EquipmentBalancedLR),
        (relative, LogisticRegressionCandidate), (relative, EquipmentBalancedLR)]
    variants = {}
    for label, (dataset, kind) in zip(VARIANTS, recipes, strict=True):
        candidate = kind(source.config_id, source.params)
        row = diagnostics.nestedClean(dataset, training.splits, candidate)
        row['equipment_cap_met'] = not row['equipment_above_budget'] and len(row['equipment_without_early_window']) < row['metrics']['engines']
        row['complete_equipment_coverage'] = not row['equipment_without_early_window']
        row['alarm_fix_candidate'] = row['clean_limits_met'] and row['equipment_cap_met'] and row['complete_equipment_coverage']
        variants[label] = row
    return {'development_ids': development.equipment_ids, 'reserved_scored': False, 'independent_validation': False,
        'config': training.config.as_dict(), 'candidate': source.name, 'source_params': source.params, 'weighting': WEIGHTING, 'variants': variants,
        'limitations': ['Exploratory reuse of twelve previously examined development bearings; not independent validation.',
            'Both weighted scaling and model fitting change together; this comparison does not isolate their individual effects.',
            'Threshold objective and the recorded pooled warning/alarm criterion are unchanged for this study.',
            'The added per-equipment adoption guard was declared before this run; it does not rewrite the previous protocol.',
            'Unavailable early windows are not zero-alarm passes and prevent complete per-equipment coverage.',
            'Prefix-relative inputs use each bearing\'s own current/past startup observations; startup is not certified healthy.',
            'Only clean telemetry is evaluated. Fault robustness, domain review and a fresh cohort are needed before promotion.',
            'No saved context, threshold, protocol, exposure record or application default was replaced.']}


def writeReport(result, path):
    lines = ['# Equipment-balanced development experiment', '',
        'Development equipment only. No reserved assessment, provider call or application default change.', '',
        '| Variant | Useful warnings | Pooled alarms | Equipment mean | Worst equipment | Above budget | Pooled limits met |',
        '|---|---:|---:|---:|---:|---:|---|']
    for label, row in result['variants'].items():
        metrics = row['metrics']
        values = [metrics['early_alarm_burden'], row['equipment_mean_burden'], row['equipment_max_burden']]
        burdens = [f'{value:.2%}' if value is not None else 'Unavailable' for value in values]
        lines.append(f"| {label} | {metrics['detected']}/{metrics['engines']} | {' | '.join(burdens)} | {len(row['equipment_above_budget'])} | {row['clean_limits_met']} |")
    lines.extend(['', '## Method', '', result['weighting'], '',
        'All four arms use the same development equipment, grouped outer splits, LR C/max_iter, feature/warning windows, threshold grid and pooled acceptance criterion. Inner grouped out-of-fold predictions select each threshold; a model fit on all outer training equipment then scores that outer group. Weights and learned scaler/imputation/model parameters never use outer evaluation rows. The relative reference uses each bearing\'s own causal startup readings and then freezes.', '',
        'The pooled protocol remains unchanged. The prospective adoption guard additionally requires every assessable bearing at or below the recorded early-alarm budget and complete early-window coverage. Missing coverage remains visible. Passing a development guard is not independent validation or deployment approval.', '', '## Paired development comparisons', ''])
    for original, weighted in (('raw_rms', 'raw_equipment_balanced'), ('relative_rms', 'relative_equipment_balanced')):
        before, after = result['variants'][original], result['variants'][weighted]
        warningChange = after['metrics']['detected'] - before['metrics']['detected']
        burdenBefore, burdenAfter = before['metrics']['early_alarm_burden'], after['metrics']['early_alarm_burden']
        change = f'{100*(burdenAfter-burdenBefore):+.2f} percentage points' if burdenBefore is not None and burdenAfter is not None else 'unavailable'
        lines.append(f'- {weighted} versus {original}: useful-warning count change {warningChange:+d}; pooled alarm-time change {change}.')
    lines.extend(['', '## Equipment outcomes', '', '| Variant | Equipment | Useful warning | Alarm minutes | Eligible minutes |', '|---|---|---|---:|---:|'])
    for label, row in result['variants'].items():
        for equipment in row['equipment']:
            lines.append(f"| {label} | {equipment['equipment_id']} | {equipment['detected']} | {equipment['alarm_eligible_cycles']} | {equipment['eligible_cycles']} |")
    lines.extend(['', '## Adoption decision', ''])
    for label in ('raw_equipment_balanced', 'relative_equipment_balanced'):
        row = result['variants'][label]
        lines.append(f"- {label}: pooled limits met={row['clean_limits_met']}; assessable-equipment alarm cap met={row['equipment_cap_met']}; complete early-window coverage={row['complete_equipment_coverage']}; development alarm-fix candidate={row['alarm_fix_candidate']}.")
    lines.extend(['', 'No variant was promoted. Improvements or regressions are descriptive results of this fixed development experiment, not evidence on new equipment. The original fifteen bearings remain exposed; any changed procedure needs another fresh cohort for an independent validation claim.', '', '## Limits', '', *['- ' + item for item in result['limitations']]])
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
    paths = [Path(__file__), Path(diagnostics.__file__)]
    protocol = {'context': evaluator.context_fingerprint, 'development_ids': training.splits.development, 'outer_folds': training.splits.folds,
        'variants': VARIANTS, 'weighting': WEIGHTING, 'baseline_window': training.config.feature_window,
        'criteria': default_criteria(training.config).model_dump(mode='json'),
        'adoption_guard': f'Pooled criteria plus <={training.config.max_early_alarm_burden:.1%} early alarms on every assessable equipment history and complete early-window coverage.',
        'threshold_selection': 'Unchanged inner grouped OOF objective; outer evaluation rows never select weights or thresholds.',
        'reserved_scored': False, 'independent_validation': False,
        'source_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}}
    (args.output / 'protocol.json').write_text(json.dumps(protocol, indent=2) + '\n', encoding='utf-8')
    for path in paths:
        (args.output / path.name).write_bytes(path.read_bytes())
    result = study(training)
    (args.output / 'results.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    writeReport(result, args.output / 'report.md')
    print(json.dumps({key: {'metrics': row['metrics'], 'worst_equipment_burden': row['equipment_max_burden'],
        'alarm_fix_candidate': row['alarm_fix_candidate']} for key, row in result['variants'].items()}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
