import json

import numpy as np
import pytest
from pydantic import ValidationError

from app.faults.evaluator import AlarmExposure, FaultEvaluation, alarmExposure, prediction_digest
from app.investigator.findings import FindingCriterion, checkCriterion, classify, digest
from app.investigator.publication import experimentRow
from app.investigator.controller import ControllerLimits, NemotronController
from app.investigator.findings import saveCriterion
from test_nemotron_controller import proposal, provider, run, setup, stop
from app.scoring.metrics import aggregate, score_engine
from test_compound_faults import fitted as fitted  # noqa: F401
from test_investigation_findings import LR, warningEvaluation


def alarmEvaluation(fitted, *, cleanNoisy=False, faultNoisy=False, short=False):
    evaluation = warningEvaluation(fitted, lost=1)
    model = next(item for item in evaluation.models if item.candidate == LR)
    clean, faulted = [], []
    for index, pair in enumerate(model.pairs):
        length = 26 if short and index == 0 else 100
        cycles = np.arange(1, length+1)
        rul = length - cycles
        beforeScores = (rul <= 15).astype(float)
        if cleanNoisy and index == 0:
            beforeScores[(rul >= 55) & (rul <= 69)] = 1
        afterScores = beforeScores.copy()
        if index == len(model.pairs)-1:
            afterScores[:] = 0
        if faultNoisy and index == 0:
            afterScores[(rul >= 55) & (rul <= 69)] = 1
        before = score_engine(pair.equipment_id, beforeScores, cycles, rul, model.threshold, config=fitted.config)
        after = score_engine(pair.equipment_id, afterScores, cycles, rul, model.threshold, config=fitted.config)
        pair.clean, pair.faulted = before.outcome, after.outcome
        pair.clean_alarm, pair.faulted_alarm = alarmExposure(before), alarmExposure(after)
        pair.clean_prediction_digest = prediction_digest(beforeScores, cycles)
        pair.faulted_prediction_digest = prediction_digest(afterScores, cycles)
        clean.append(before)
        faulted.append(after)
    model.clean_all = model.clean_matched = aggregate(clean, config=fitted.config)
    model.faulted = aggregate(faulted, config=fitted.config)
    return evaluation


def test_version_one_criteria_keep_their_original_payload_and_fingerprint():
    payload = {'version': 1, 'candidate': LR, 'min_coverage': .8, 'min_histories': 10, 'min_clean_detection': .8,
        'min_lost_warnings': 1, 'max_alarm_burden': .05, 'min_burden_increase': .01}
    criterion = FindingCriterion.model_validate(payload)
    assert criterion.model_dump(mode='json') == payload
    assert json.loads(criterion.model_dump_json()) == payload
    assert criterion.fingerprint == digest(payload)
    with pytest.raises(ValidationError):
        FindingCriterion(version=1, candidate=LR, alarm_scope='per_equipment')
    copied = criterion.model_copy(update={'alarm_scope': 'per_equipment'})
    with pytest.raises(ValueError, match='version2'):
        checkCriterion(copied, {LR})


def test_legacy_evaluation_serialization_does_not_invent_alarm_evidence(fitted):
    original = alarmEvaluation(fitted).model_dump(mode='json')
    for model in original['models']:
        for pair in model['pairs']:
            pair.pop('clean_alarm', None)
            pair.pop('faulted_alarm', None)
    restored = FaultEvaluation.model_validate(original)
    assert restored.model_dump(mode='json') == original
    assert digest(restored.model_dump(mode='json')) == digest(original)


def test_per_equipment_scope_rejects_a_noisy_clean_bearing_hidden_by_pooling(fitted):
    evaluation = alarmEvaluation(fitted, cleanNoisy=True)
    model = next(item for item in evaluation.models if item.candidate == LR)
    assert model.clean_matched.early_alarm_burden < .05
    pooled = classify(evaluation, FindingCriterion(candidate=LR))
    capped = classify(evaluation, FindingCriterion(version=2, candidate=LR, alarm_scope='per_equipment'))
    assert pooled.status == 'measured_failure'
    assert capped.status == 'inconclusive'
    assert any('per-equipment alarm cap' in reason for reason in capped.reasons)
    assert len(capped.equipment_alarms) == evaluation.evaluated_histories
    row = capped.equipment_alarms[0]
    assert row.clean.alarm_eligible_cycles / row.clean.eligible_cycles > .05


def test_per_equipment_fault_effect_is_detected_below_the_pooled_limit(fitted):
    evaluation = alarmEvaluation(fitted, faultNoisy=True)
    model = next(item for item in evaluation.models if item.candidate == LR)
    assert model.faulted.early_alarm_burden < .05
    pooled = classify(evaluation, FindingCriterion(candidate=LR, min_lost_warnings=1000))
    capped = classify(evaluation, FindingCriterion(version=2, candidate=LR, alarm_scope='per_equipment', min_lost_warnings=1000))
    assert pooled.status == 'no_measured_failure'
    assert capped.status == 'measured_failure'
    effect = next(item for item in capped.effects if item.kind == 'alarm_burden')
    assert effect.histories == (model.pairs[0].equipment_id,)
    assert effect.clean_value is None and effect.faulted_value is None


@pytest.mark.parametrize('legacy', [False, True])
def test_missing_or_empty_per_equipment_windows_are_not_passes(fitted, legacy):
    evaluation = alarmEvaluation(fitted, short=not legacy)
    model = next(item for item in evaluation.models if item.candidate == LR)
    if legacy:
        model.pairs[0].clean_alarm = None
    finding = classify(evaluation, FindingCriterion(version=2, candidate=LR, alarm_scope='per_equipment'))
    assert finding.status == 'inconclusive'
    assert any('Per-equipment alarm evidence is unavailable' in reason for reason in finding.reasons)


def test_alarm_exposure_enforces_observed_denominators():
    for values in ({'eligible_cycles': 10, 'alarm_eligible_cycles': 11, 'scored_cycles': 20},
        {'eligible_cycles': 21, 'alarm_eligible_cycles': 1, 'scored_cycles': 20}):
        with pytest.raises(ValidationError):
            AlarmExposure(**values)


def test_public_finding_reasons_do_not_reveal_private_equipment_identifiers(fitted):
    evaluation = alarmEvaluation(fitted, cleanNoisy=True)
    model = next(item for item in evaluation.models if item.candidate == LR)
    pair = model.pairs[0]
    private = 'PRIVATE-ASSET-987X'
    pair.equipment_id = private
    pair.clean.equipment_id = private
    pair.faulted.equipment_id = private
    finding = classify(evaluation, FindingCriterion(version=2, candidate=LR, alarm_scope='per_equipment'))
    assert private in finding.model_dump_json()
    assert private not in json.dumps(experimentRow(finding, 1))


def test_v2_controller_sees_scope_and_anonymous_machine_alarm_evidence(fitted, tmp_path, monkeypatch):
    engine, store, id, settings = setup(fitted, tmp_path)
    equipment = engine.cleanEquipment()
    rows = equipment[LR]
    before = rows[0]['exposure']
    rows[0]['exposure'] = before.model_copy(update={'alarm_eligible_cycles': int(before.eligible_cycles*.2)})
    metrics = engine.cleanMetrics()
    pooled = sum(row['exposure'].alarm_eligible_cycles for row in rows) / sum(row['exposure'].eligible_cycles for row in rows)
    metrics[LR] = metrics[LR].model_copy(update={'early_alarm_burden': pooled})
    monkeypatch.setattr(engine, 'cleanEquipment', lambda: equipment)
    monkeypatch.setattr(engine, 'cleanMetrics', lambda: metrics)
    saveCriterion(store, id, FindingCriterion(version=2, candidate=LR, alarm_scope='per_equipment'))
    controller = NemotronController(store, engine, settings)
    packet = controller.packet(store.get(id), ControllerLimits())
    assert packet['criterion']['version'] == 2
    assert packet['criterion']['alarmScope'] == 'per_equipment'
    assert packet['criterion']['minCleanDetection'] == .8
    assert packet['clean'][0]['equipmentAlarm']['available'] == 22
    assert packet['clean'][0]['equipmentAlarm']['missing'] == 0
    assert packet['clean'][0]['alarmBurden'] < .05
    assert packet['clean'][0]['equipmentAlarm']['worst'] > .05
    text = json.dumps(packet)
    assert all(f'"{equipment}"' not in text for equipment in engine.snapshot().splits.development)


def test_completed_v2_controller_packet_keeps_anonymous_paired_alarm_summaries(fitted, tmp_path, monkeypatch):
    engine, store, id, settings = setup(fitted, tmp_path)
    saveCriterion(store, id, FindingCriterion(version=2, candidate=LR, alarm_scope='per_equipment'))
    calls = provider(monkeypatch, [proposal(), stop()])
    run(store, engine, settings, id, maxCalls=2, maxOutputTokens=128, maxCompletionTokens=256)
    experiment = calls[1]['experiments'][0]
    row = experiment['models'][0]
    assert row['cleanEquipmentAlarm']['histories'] == experiment['evaluatedHistories']
    assert row['faultedEquipmentAlarm']['available'] + row['faultedEquipmentAlarm']['missing'] == experiment['evaluatedHistories']
    assert 'findingReasons' in experiment
    assert all(f'"{equipment}"' not in json.dumps(calls) for equipment in engine.snapshot().splits.development)
