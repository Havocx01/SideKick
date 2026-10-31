"""Read-only threshold checks on saved development predictions."""
import time

import numpy as np

from app.faults.evaluator import alarmExposure
from app.investigator.findings import warningState
from app.investigator.schemas import CleanEquipment, CleanMetrics, ThresholdCheck, ThresholdPoint
from app.scoring.metrics import aggregate, score_engine


def thresholdPoint(perEngine, threshold, config, *, check=None):
    scorings, equipment = [], []
    for id, row in sorted(perEngine.items()):
        if check is not None:
            check()
        scoring = score_engine(id, row.scores, row.cycles, row.rul, threshold, config=config)
        if check is not None:
            check()
        scorings.append(scoring)
        equipment.append(CleanEquipment(equipment_id=id, warning=warningState(scoring.outcome), exposure=alarmExposure(scoring)))
    metrics = aggregate(scorings, config=config)
    burdens = [item.exposure.burden for item in equipment if item.exposure.burden is not None]
    clean = CleanMetrics(detection=metrics.detection_fraction, alarmBurden=metrics.early_alarm_burden,
        medianLead=metrics.median_lead_time, histories=metrics.engines, equipment=equipment,
        meanEquipmentBurden=float(np.mean(burdens)) if burdens else None, worstEquipmentBurden=max(burdens) if burdens else None)
    return ThresholdPoint(threshold=float(threshold), clean=clean)


def assessThresholds(perEngine, current, criterion, config, context, *, maxSeconds=30, deadline=None, checkpoint=None):
    deadline = time.monotonic()+maxSeconds if deadline is None else deadline

    def check():
        if checkpoint is not None:
            checkpoint()
        if time.monotonic() >= deadline:
            raise ValueError('Threshold check exceeded its time allowance')

    check()
    if not perEngine:
        raise ValueError('No recorded development predictions are available')
    scores = np.concatenate([row.scores for row in perEngine.values()])
    values = np.unique(scores[np.isfinite(scores)])
    if not len(values):
        raise ValueError('Development predictions have no finite scores')
    thresholds = np.append(values, np.nextafter(values[-1], np.inf))
    check()
    cache = {}

    def evaluate(index):
        check()
        if index not in cache:
            cache[index] = thresholdPoint(perEngine, float(thresholds[index]), config, check=check)
        return cache[index]

    def burden(point):
        return point.clean.worstEquipmentBurden if criterion.alarm_scope == 'per_equipment' else point.clean.alarmBurden

    baseline = thresholdPoint(perEngine, current, config, check=check)
    result = {'contextFingerprint': context, 'criterion': criterion, 'current': baseline, 'candidateThresholds': len(thresholds)}
    if burden(evaluate(0)) is None:
        return ThresholdCheck(status='insufficient_evidence', suggested=None, bestWithinAlarmCap=None,
            reasons=['No eligible early-alarm window was recorded.'], evaluatedThresholds=len(cache), **result)
    low, high = 0, len(thresholds)-1
    while low < high:
        middle = (low+high) // 2
        if burden(evaluate(middle)) <= criterion.max_alarm_burden:
            high = middle
        else:
            low = middle+1
    maximumWarnings = evaluate(low).clean.detection
    high = len(thresholds)-1
    while low < high:
        middle = (low+high+1) // 2
        if evaluate(middle).clean.detection == maximumWarnings:
            low = middle
        else:
            high = middle-1
    best = evaluate(low)
    reasons, missing = [], [item.equipment_id for item in best.clean.equipment if item.exposure.burden is None]
    insufficient = best.clean.histories < criterion.min_histories or (criterion.alarm_scope == 'per_equipment' and bool(missing))
    if best.clean.histories < criterion.min_histories:
        reasons.append(f'{best.clean.histories} histories is below the required {criterion.min_histories}.')
    if criterion.alarm_scope == 'per_equipment' and missing:
        reasons.append('Early-alarm coverage is missing for: ' + ', '.join(missing))
    if best.clean.detection < criterion.min_clean_detection:
        reasons.append(f'At most {best.clean.detection:.1%} useful warnings meet the alarm cap; {criterion.min_clean_detection:.1%} is required.')
    status = 'insufficient_evidence' if insufficient else 'no_qualifying_threshold' if reasons else 'qualified'
    return ThresholdCheck(status=status, suggested=best if status == 'qualified' else None, bestWithinAlarmCap=best,
        reasons=reasons, evaluatedThresholds=len(cache), **result)
