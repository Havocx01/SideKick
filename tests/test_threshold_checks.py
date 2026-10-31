import numpy as np
import pytest

from app.investigator.findings import FindingCriterion
from app.investigator.schemas import ThresholdCheckRequest
from app.investigator import thresholds
from app.investigator.thresholds import assessThresholds
from test_bearing_cap import CONFIG, capped, history, timely
from test_compound_faults import fitted as fitted  # noqa: F401
from test_investigations_api import HEADERS, LR, api as api  # noqa: F401


@pytest.mark.parametrize('noisy', [False, True])
def test_product_selector_matches_the_verified_research_cutoff(noisy):
    rows = {'one': timely('one'), 'two': timely('two')}
    if noisy:
        rows['one'] = history('one', np.full(80, .9))
    criterion = FindingCriterion(version=2, candidate=LR, alarm_scope='per_equipment', min_histories=1)
    result = assessThresholds(rows, .5, criterion, CONFIG, 'context')
    expected = capped.chooseCapped(rows, CONFIG)
    assert (result.status == 'qualified') == expected['qualified']
    assert result.bestWithinAlarmCap.threshold == expected['diagnostic_threshold']
    assert result.bestWithinAlarmCap.clean.detection == expected['best_capped']['metrics']['detection_fraction']
    assert result.suggested is None if not expected['qualified'] else result.suggested.threshold == expected['threshold']


def test_scope_distinguishes_pooled_dilution_from_machine_caps():
    noisy = timely('noisy')
    noisy.scores[:10] = .9
    rows = {'noisy': noisy, 'long': timely('long', 2000)}
    pooled = assessThresholds(rows, .9, FindingCriterion(candidate=LR, min_histories=1), CONFIG, 'context')
    strict = assessThresholds(rows, .9, FindingCriterion(version=2, candidate=LR, alarm_scope='per_equipment', min_histories=1), CONFIG, 'context')
    assert pooled.status == 'qualified' and pooled.suggested.clean.worstEquipmentBurden > .05
    assert strict.status == 'no_qualifying_threshold' and strict.suggested is None


def test_missing_windows_and_small_samples_are_insufficient_evidence():
    rows = {'long': timely('long'), 'short': timely('short', 25)}
    criterion = FindingCriterion(version=2, candidate=LR, alarm_scope='per_equipment', min_histories=10)
    result = assessThresholds(rows, .9, criterion, CONFIG, 'context')
    assert result.status == 'insufficient_evidence' and result.suggested is None
    assert any('below the required' in reason for reason in result.reasons)
    assert any('short' in reason for reason in result.reasons)


def test_selector_has_a_bounded_time_allowance():
    with pytest.raises(ValueError, match='time allowance'):
        assessThresholds({'one': timely()}, .5, FindingCriterion(candidate=LR), CONFIG, 'context', maxSeconds=-1)


def test_api_check_is_read_only_and_exposes_real_equipment_counts(api):
    client, service, _ = api
    before = client.get('/api/investigations/contexts').json()[0]
    response = client.post('/api/investigations/contexts/synthetic/threshold-check', headers=HEADERS,
        json={'criterion': {'version': 2, 'candidate': LR, 'alarm_scope': 'pooled'}})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['status'] == 'qualified'
    assert result['criterion']['version'] == 2
    assert len(result['current']['clean']['equipment']) == 22
    assert result['contextFingerprint'] == before['contextFingerprint']
    after = client.get('/api/investigations/contexts').json()[0]
    assert before == after
    assert client.get('/api/investigations', headers=HEADERS).json() == []
    assert all(item['exposure']['alarm_eligible_cycles'] <= item['exposure']['eligible_cycles'] for item in result['current']['clean']['equipment'])
    engine = service.evaluator('synthetic')
    scores = engine.calibrationScores(LR)
    assert set(scores) == set(engine.snapshot().splits.development)
    assert not set(scores) & set(engine.snapshot().splits.holdout)


def test_api_rejects_invalid_scope_origins_and_concurrent_checks(api):
    client, service, _ = api
    path = '/api/investigations/contexts/synthetic/threshold-check'
    assert client.post(path, headers=HEADERS, json={'criterion': {'version': 1, 'candidate': LR, 'alarm_scope': 'per_equipment'}}).status_code == 422
    assert client.post(path, headers={**HEADERS, 'origin': 'https://unrelated.test'}, json={'criterion': {'candidate': LR}}).status_code == 403
    service.thresholdLock.acquire()
    try:
        response = client.post(path, headers=HEADERS, json={'criterion': {'candidate': LR}})
        assert response.status_code == 409
        assert service.thresholdLock.locked()
    finally:
        service.thresholdLock.release()


def test_setup_time_counts_against_the_same_threshold_budget(api, monkeypatch):
    _, service, _ = api
    engine = service.evaluator('synthetic')
    clock = [100.]
    monkeypatch.setattr(thresholds.time, 'monotonic', lambda: clock[0])

    def load(name):
        clock[0] += 31
        return engine

    monkeypatch.setattr(service, 'evaluator', load)
    monkeypatch.setattr(engine, 'calibrationScores', lambda *args, **kwargs: pytest.fail('Expired setup must not start prediction'))
    with pytest.raises(ValueError, match='time allowance'):
        service.checkThreshold('synthetic', ThresholdCheckRequest(criterion=FindingCriterion(candidate=LR)))
    assert not service.thresholdLock.locked()


def test_single_point_work_checks_deadline_between_histories(monkeypatch):
    clock, calls = [100.], []
    original = thresholds.score_engine
    monkeypatch.setattr(thresholds.time, 'monotonic', lambda: clock[0])

    def score(*args, **kwargs):
        calls.append(args[0])
        result = original(*args, **kwargs)
        clock[0] += 2
        return result

    monkeypatch.setattr(thresholds, 'score_engine', score)
    with pytest.raises(ValueError, match='time allowance'):
        assessThresholds({'one': timely('one'), 'two': timely('two')}, .5, FindingCriterion(candidate=LR), CONFIG, 'context', maxSeconds=1)
    assert len(calls) == 1
