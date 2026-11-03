"""Compare raw and causal prefix-relative RMS on development equipment only.

Thresholds are chosen inside each outer training split. This is exploratory
development reuse, not a new independent assessment or a change to app defaults.
"""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

import numpy as np

from app.faults.replay import load_trusted_context
from app.models.candidates import LogisticRegressionCandidate
from app.models.design import design_from_blocks, engine_blocks
from app.models.splits import validate_splits
from app.models.train import fit_final, train_development
from app.schemas import SplitAssignment
from app.scoring.metrics import aggregate, score_engine
from app.scoring.pipeline import pick_thresholds
from app.scoring.selection import default_criteria


def relativeRms(dataset, window):
    if type(window) is not int or window < 1:
        raise ValueError('The RMS baseline window must be a positive integer')
    frame = dataset.frame.copy()
    for equipment in dataset.equipment_ids:
        start, stop = dataset.rows_for(equipment)
        values = dataset.sensor_matrix(equipment)
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError('Relative RMS requires nonnegative finite clean readings')
        count = np.minimum(np.arange(1, len(values)+1), window)
        prefix = np.cumsum(values[:window], axis=0)
        baseline = prefix[count-1] / count[:, None]
        # A zero-only prefix has no relative scale; use one source unit until a positive baseline exists.
        reference = np.where(baseline > 0, baseline, 1.)
        frame.loc[frame.index[start:stop], dataset.sensors] = np.log1p(values / reference)
    identity = hashlib.sha256(f'{dataset.data_hash}:prefix-relative-rms-v1:{window}'.encode()).hexdigest()
    return replace(dataset, frame=frame, data_hash=identity)


def scoreDesign(model, builder, dataset, threshold):
    blocks = engine_blocks(dataset, builder)
    design = design_from_blocks(blocks, builder.feature_names())
    scores = model.score(design)
    scorings, equipment = [], []
    for id in dataset.equipment_ids:
        mask = design.equipment_id == id
        scoring = score_engine(id, scores[mask], design.cycle[mask], design.rul[mask], threshold, config=dataset.config)
        scorings.append(scoring)
        equipment.append(equipmentSummary(scoring, scores[mask], design.rul[mask], dataset.config))
    return scorings, equipment


def equipmentSummary(scoring, scores, rul, config):
    early = np.asarray(scores)[np.asarray(rul) > config.transition_band_end]
    return {**scoring.outcome.model_dump(mode='json'), 'eligible_cycles': scoring.eligible_cycles,
        'alarm_eligible_cycles': scoring.alarm_eligible_cycles, 'scored_cycles': scoring.scored_cycles,
        'early_alarm_burden': scoring.alarm_eligible_cycles / scoring.eligible_cycles if scoring.eligible_cycles else None,
        'early_score_median': float(np.median(early)) if len(early) else None,
        'early_score_p95': float(np.quantile(early, .95)) if len(early) else None}


def cleanSummary(scorings, equipment, config):
    burdens = [row['early_alarm_burden'] for row in equipment if row['early_alarm_burden'] is not None]
    metrics = aggregate(scorings, config=config)
    return {'metrics': metrics.model_dump(mode='json'), 'equipment': equipment,
        'equipment_mean_burden': float(np.mean(burdens)) if burdens else None,
        'equipment_max_burden': max(burdens) if burdens else None,
        'equipment_above_budget': [row['equipment_id'] for row in equipment if row['early_alarm_burden'] is not None
            and row['early_alarm_burden'] > config.max_early_alarm_burden],
        'equipment_without_early_window': [row['equipment_id'] for row in equipment if row['early_alarm_burden'] is None],
        'clean_limits_met': metrics.detection_fraction >= config.min_detection_fraction
            and metrics.early_alarm_burden is not None and metrics.early_alarm_burden <= config.max_early_alarm_burden}


def nestedClean(dataset, splits, candidate):
    validate_splits(splits)
    if len(splits.folds) < 3:
        raise ValueError('Nested grouped evaluation needs at least three outer folds')
    if set(dataset.equipment_ids) != set(splits.development):
        raise ValueError('Nested evaluation accepts only the development subset')
    scorings, equipment, folds = [], [], []
    for index, evaluationIds in enumerate(splits.folds):
        innerFolds = [list(ids) for other, ids in enumerate(splits.folds) if other != index]
        trainingIds = [id for ids in innerFolds for id in ids]
        config = replace(dataset.config, n_folds=len(innerFolds), holdout_engines=0)
        trainingData = replace(dataset.subset(trainingIds), config=config)
        inner = SplitAssignment(holdout=[], development=trainingIds, folds=innerFolds, seed=splits.seed, config_fingerprint=config.fingerprint())
        training = train_development(trainingData, config=config, candidates=[candidate], splits=inner)
        choice = pick_thresholds(training, default_criteria(config), config=config)[candidate.name]
        model, builder, _ = fit_final(trainingData, inner, candidate, config=config)
        current, rows = scoreDesign(model, builder, dataset.subset(evaluationIds), choice.threshold)
        scorings.extend(current)
        equipment.extend(rows)
        folds.append({'fold': index, 'threshold_ids': trainingIds, 'evaluation_ids': list(evaluationIds), 'threshold': choice.threshold,
            'calibration': choice.metrics.model_dump(mode='json'), 'calibration_within_budget': choice.within_budget,
            'evaluation': aggregate(current, config=config).model_dump(mode='json')})
    return {**cleanSummary(scorings, equipment, dataset.config), 'folds': folds}


def study(training, thresholds):
    names = [name for name, model in training.specs.items() if isinstance(model, LogisticRegressionCandidate) and name in thresholds]
    if len(names) != 1:
        raise ValueError('Select a context containing exactly one logistic-regression candidate')
    name = names[0]
    candidate, config = training.specs[name], training.config
    development = training.dataset.subset(training.splits.development)
    oldScorings, oldEquipment = [], []
    for fold in training.folds:
        current, rows = scoreDesign(fold.candidates[name], fold.builder, development.subset(fold.validation_engines), thresholds[name])
        oldScorings.extend(current)
        oldEquipment.extend(rows)
    model, builder, _ = fit_final(development, training.splits, candidate, config=config)
    refitScorings, refitEquipment = scoreDesign(model, builder, development, thresholds[name])
    support = []
    scorable = development.scorable_mask()
    for id in development.equipment_ids:
        start, stop = development.rows_for(id)
        rows = int(scorable[start:stop].sum())
        support.append({'equipment_id': id, 'recordings': stop-start, 'training_rows': rows, 'training_row_share': rows / int(scorable.sum()),
            'prefix_mean_rms': dict(zip(development.sensors, development.sensor_matrix(id)[:config.feature_window].mean(axis=0).tolist(), strict=True))})
    normalized = relativeRms(development, config.feature_window)
    return {'development_ids': development.equipment_ids, 'reserved_scored': False, 'independent_validation': False,
        'candidate': name, 'params': candidate.params, 'config': config.as_dict(), 'support': support,
        'original_threshold': thresholds[name], 'original_oof': cleanSummary(oldScorings, oldEquipment, config),
        'refit_in_sample': cleanSummary(refitScorings, refitEquipment, config),
        'variants': {'raw_rms': nestedClean(development, training.splits, candidate),
            'relative_rms': nestedClean(normalized, training.splits, candidate)},
        'limitations': ['Exploratory reuse of previously examined development equipment, not independent validation.',
            'Original OOF scores selected their own threshold; the refit diagnostic is in-sample, not generalization.',
            'Nested thresholds use inner equipment only; outer results must not be used to pick another threshold.',
            'Prefix-relative RMS uses the first feature_window recordings and then freezes that baseline; startup is not known healthy.',
            'A zero-only baseline falls back to one source unit; this assumption needs domain review.',
            'Only clean telemetry is evaluated. Fault robustness and independent equipment validation remain untested for this transform.',
            'No saved source-context model or threshold, source protocol, exposure ledger or application default was replaced. Temporary diagnostic models were fitted.']}


def writeReport(result, path):
    lines = ['# Development clean-alarm diagnosis', '', 'Development reuse only. No reserved histories were rescored and no application defaults changed.', '',
        '| Procedure | Useful warnings | Pooled early-alarm time | Equipment mean early-alarm time | Existing pooled limits met |', '|---|---:|---:|---:|---|']
    procedures = {'Original OOF (threshold selected on these scores)': result['original_oof'],
        'Final refit (in-sample diagnostic)': result['refit_in_sample'], **result['variants']}
    for label, row in procedures.items():
        metrics = row['metrics']
        burden = f"{metrics['early_alarm_burden']:.2%}" if metrics['early_alarm_burden'] is not None else 'Unavailable'
        mean = f"{row['equipment_mean_burden']:.2%}" if row['equipment_mean_burden'] is not None else 'Unavailable'
        lines.append(f"| {label} | {metrics['detected']}/{metrics['engines']} | {burden} | {mean} | {row['clean_limits_met']} |")
    lines.extend(['', 'Raw and relative variants use nested grouped evaluation: thresholds, imputation, scaler and model are learned on outer training equipment only. The relative-RMS reference uses each evaluated bearing\'s own causal startup readings, current and past only, then freezes after the baseline window; it does not use future readings or failure labels. All variants use the same LR settings, warning windows and acceptance criteria. These results describe one fixed exploratory comparison, not a deployed remedy or new independent evidence.', '',
        '## Alarm concentration warnings', '', 'The existing protocol uses pooled eligible time, not equal equipment weights or a worst-equipment cap. Passing that gate can hide high alarms on short histories. The following are diagnostic warnings, not retrospectively changed acceptance criteria.', ''])
    for label, row in procedures.items():
        worst = f"{row['equipment_max_burden']:.2%}" if row['equipment_max_burden'] is not None else 'Unavailable'
        lines.append(f"- {label}: maximum equipment burden {worst}; above the pooled budget when assessed individually: {', '.join(row['equipment_above_budget']) or 'none'}; no eligible early window: {', '.join(row['equipment_without_early_window']) or 'none'}.")
    lines.extend(['', '## Equipment-level nested results', '',
        '| Variant | Equipment | Useful warning | Early-alarm minutes | Eligible minutes |', '|---|---|---|---:|---:|'])
    for variant, row in result['variants'].items():
        for equipment in row['equipment']:
            lines.append(f"| {variant} | {equipment['equipment_id']} | {equipment['detected']} | {equipment['alarm_eligible_cycles']} | {equipment['eligible_cycles']} |")
    if result['variants']['relative_rms']['equipment_above_budget']:
        lines.extend(['', '## Remedy decision', '', 'Prefix-relative normalization did not resolve concentrated clean alarms: at least one bearing still exceeds the alarm budget when examined individually. A pooled pass alone is insufficient evidence to promote this transform as an alarm fix. No candidate was promoted. Fault robustness and fresh-equipment performance remain untested for this transform.'])
    lines.extend(['', '## Limits', '', *['- ' + item for item in result['limitations']], '',
        'Further development may use these twelve histories, but a changed procedure requires another fresh equipment cohort for an independent validation claim. The three previously assessed bearings remain exposed.'])
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
    protocol = {'context': evaluator.context_fingerprint, 'development_ids': training.splits.development, 'outer_folds': training.splits.folds,
        'variants': ['raw_rms', 'relative_rms'], 'baseline_window': training.config.feature_window,
        'threshold_selection': 'Inner grouped OOF only; final outer model fit on inner development histories.',
        'acceptance': default_criteria(training.config).model_dump(mode='json'), 'reserved_scored': False, 'independent_validation': False,
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (args.output / 'protocol.json').write_text(json.dumps(protocol, indent=2) + '\n', encoding='utf-8')
    result = study(training, evaluator.thresholds)
    assert result['original_oof']['metrics'] == evaluator.cleanMetrics()[result['candidate']].model_dump(mode='json')
    (args.output / 'results.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    writeReport(result, args.output / 'report.md')
    print(json.dumps({key: row['metrics'] for key, row in result['variants'].items()}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
