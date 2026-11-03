"""Check a threshold remedy across development folds and an all-development refit."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))

import joblib
import numpy as np

from app.faults.evaluator import FixedDevelopmentEvaluator
from app.faults.replay import load_trusted_context
from app.faults.scenarios import FaultCase
from app.investigator.findings import FindingCriterion, alarmSummary, classify
from app.models.train import FoldFit, TrainingResult, fit_final, train_development
from app.schemas import SplitAssignment

THRESHOLDS = (.95, .5, .4, .3, .2, .1)
SEEDS = (20261031, 20261032, 20261033)


def caseSuite(evidence):
    cases = {}
    proposals = [row['scenario'] for row in evidence.get('experiments', [])]
    proposals += [row['final'] for row in evidence.get('reductions', [])]
    for proposal in proposals:
        case = FaultCase.model_validate(proposal)
        cases[case.scenario_id] = case
    if not cases:
        raise ValueError('Provide measured development cases or completed reductions')
    return list(cases.values())


def fitVariants(training, candidate, seeds):
    yield 'original_grouped_oof', training
    ids = sorted(training.splits.development)
    final, builder, preprocessor = fit_final(training.dataset, training.splits, training.specs[candidate], config=training.config)
    splits = SplitAssignment(development=ids, holdout=[], folds=[ids], seed=training.splits.seed,
        config_fingerprint=training.config.fingerprint())
    refit = TrainingResult(training.dataset, splits, [FoldFit(0, [], ids, preprocessor, builder, {candidate: final})],
        {}, training.specs, training.config)
    yield 'all_development_refit_in_sample_diagnostic', refit

    for seed in seeds:
        order = list(np.random.default_rng(seed).permutation(ids))
        splits = SplitAssignment(development=ids, holdout=[], folds=[sorted(order[::2]), sorted(order[1::2])],
            seed=seed, config_fingerprint=training.config.fingerprint())
        fitted = train_development(training.dataset, config=training.config, splits=splits, candidates=[training.specs[candidate]])
        yield f'development_resplit_{seed}', fitted


def withinCap(alarms, maximum):
    return alarms['missing'] == 0 and alarms['worst'] is not None and alarms['worst'] <= maximum


def thresholdRows(training, cases, criterion, policy, thresholds, label):
    rows = []
    for threshold in thresholds:
        engine = FixedDevelopmentEvaluator(training, {criterion.candidate: threshold}, policy)
        clean = engine.cleanMetrics()[criterion.candidate]
        cleanAlarms = alarmSummary([row['exposure'] for row in engine.cleanEquipment()[criterion.candidate]])
        for case in cases:
            result = engine.evaluate(case)
            finding = classify(result, criterion)
            model = result.models[0]
            faultAlarms = alarmSummary([pair.faulted_alarm for pair in model.pairs])
            lost = [pair for pair in model.pairs if pair.clean.detected and not pair.faulted.detected]
            meets = (finding.status == 'no_measured_failure' and result.evaluated_histories == result.expected_histories
                and clean.engines >= criterion.min_histories
                and clean.detection_fraction >= criterion.min_clean_detection and withinCap(cleanAlarms, criterion.max_alarm_burden)
                and withinCap(faultAlarms, criterion.max_alarm_burden))
            rows.append({'fit': label, 'threshold': threshold, 'case': case.scenario_id, 'status': finding.status,
                'evaluated': finding.evaluated_histories, 'expected': result.expected_histories, 'cleanDetection': finding.clean_detection,
                'faultedDetection': finding.faulted_detection, 'cleanBurden': clean.early_alarm_burden,
                'faultedBurden': finding.faulted_burden, 'cleanWorstBurden': cleanAlarms['worst'],
                'faultedWorstBurden': faultAlarms['worst'], 'lostUsefulWarnings': len(lost),
                'lateWarnings': sum(pair.faulted.late for pair in lost), 'reasons': list(finding.reasons),
                'meetsDevelopmentLimits': meets})
    return rows


def chooseThreshold(rows, thresholds):
    for threshold in sorted(thresholds, reverse=True):
        matched = [row for row in rows if row['threshold'] == threshold]
        if matched and all(row['meetsDevelopmentLimits'] for row in matched):
            return threshold
    return None


def diagnose(evaluator, cases, criterion, *, thresholds=THRESHOLDS, seeds=SEEDS):
    if evaluator.rawSource is not None:
        raise ValueError('This diagnostic supports feature-channel faults, not raw vibration refits')
    training = evaluator.snapshot()
    ids = set(training.splits.development)
    if set(training.dataset.equipment_ids) != ids or ids & set(training.splits.holdout):
        raise ValueError('Remedy diagnostics require development-only histories')
    if criterion.candidate not in evaluator.thresholds:
        raise ValueError('Choose a candidate from the fixed development context')
    if not cases or not thresholds or any(isinstance(value, bool) or not np.isfinite(value) for value in thresholds):
        raise ValueError('Provide development cases and finite numeric thresholds')

    rows, fits = [], []
    for label, fitted in fitVariants(training, criterion.candidate, seeds):
        rows += thresholdRows(fitted, cases, criterion, evaluator.policy, thresholds, label)
        fits.append({'name': label, 'modelHashes': [joblib.hash(fold.candidates[criterion.candidate]) for fold in fitted.folds]})
    return {'developmentHistories': len(ids), 'criterion': criterion.model_dump(mode='json'), 'fits': fits, 'results': rows,
        'proposedThreshold': chooseThreshold(rows, thresholds), 'independentValidation': False,
        'selection': 'Highest supplied threshold passing every fit and known case with full history coverage and per-machine clean and faulted alarm caps.',
        'note': 'The all-development refit is scored in-sample as a diagnostic. No threshold was applied. A changed procedure needs new unseen validation.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context', required=True, type=Path)
    parser.add_argument('--trust-local-artifact', action='store_true', help='Only for a package you produced and trust; joblib can execute code.')
    parser.add_argument('--evidence', required=True, type=Path, help='Existing public evidence; only development experiments, reductions and criterion are used.')
    parser.add_argument('--output', required=True, type=Path, help='New output directory; previous results are preserved.')
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False)
    evaluator = load_trusted_context(args.context, trusted=args.trust_local_artifact)
    evidence = json.loads(args.evidence.read_text(encoding='utf-8'))
    context = evidence.get('context', {})
    if context.get('fingerprint') != evaluator.context_fingerprint or context.get('policyFingerprint') != evaluator.policy.fingerprint:
        raise ValueError('Evidence belongs to a different fixed context or fault policy')
    criterion, cases = FindingCriterion.model_validate(evidence['criterion']), caseSuite(evidence)
    protocol = {'context': evaluator.context_fingerprint, 'criterion': criterion.model_dump(mode='json'),
        'thresholds': THRESHOLDS, 'developmentFoldSeeds': SEEDS, 'cases': [case.scenario_id for case in cases],
        'scriptSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'evidenceSha256': hashlib.sha256(args.evidence.read_bytes()).hexdigest(), 'freshDataUsed': False,
        'reservedDataUsed': False, 'paidCalls': 0, 'independentValidation': False}
    (args.output / 'protocol.json').write_text(json.dumps(protocol, indent=2) + '\n', encoding='utf-8')
    result = diagnose(evaluator, cases, criterion)
    (args.output / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'developmentHistories': result['developmentHistories'], 'proposedThreshold': result['proposedThreshold'],
        'independentValidation': False, 'note': result['note']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
