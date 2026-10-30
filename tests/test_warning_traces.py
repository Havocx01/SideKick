"""Read-only score/warning excerpts use actual stored observations, not rescore jobs."""
import json

from app.assistant.warning_traces import matched_trace, MAX_TRACE_POINTS
from app.schemas import ReplayPoint
from test_deep_evidence_inputs import enriched, packet_for
from test_deep_investigation import deep_app as deep_app


def test_exact_alignment_and_no_private_readings(deep_app):
    _, original = deep_app
    bundle = enriched(original)
    before = bundle.model_dump_json()
    clean, faulted = bundle.replay_series
    trace = matched_trace(clean, faulted, bundle.development_selection.criteria)
    assert trace['status'] == 'available'
    assert trace['sampled_points'] == len(faulted.points)
    assert not trace['useful_window_complete']
    for index, sample in enumerate(trace['points']):
        assert sample['rul'] == faulted.points[index].rul
        assert sample['clean_score'] == clean.points[index].score
        assert sample['faulted_score'] == faulted.points[index].score
        assert sample['clean_warning_active'] == clean.points[index].alert
        assert sample['faulted_warning_active'] == faulted.points[index].alert
    assert '987654321' not in json.dumps(trace) and '123456789' not in json.dumps(trace)
    assert 'equipment_id' not in json.dumps(trace) and 'sensor_clean' not in json.dumps(trace)
    assert bundle.model_dump_json() == before


def test_invalid_scores_hold_persistence_and_do_not_become_zero(deep_app):
    _, original = deep_app
    bundle = enriched(original)
    clean, faulted = bundle.replay_series
    points = [ReplayPoint(cycle=cycle, rul=100-cycle, score=score, alert=alert)
              for cycle, score, alert in [(70, 1., False), (71, float('nan'), False), (72, 1., True),
                                           (80, float('inf'), True), (81, .1, True), (82, .1, False)]]
    clean.points = points
    faulted.points = [point.model_copy(deep=True) for point in points]
    clean.threshold = faulted.threshold = .5
    trace = matched_trace(clean, faulted, bundle.development_selection.criteria)
    assert trace['points'][1]['faulted_score'] is None
    assert trace['points'][1]['faulted_high_streak'] == 1
    assert trace['points'][2]['faulted_high_streak'] == 2
    assert trace['points'][3]['faulted_warning_active'] is True
    assert trace['cycle_gaps_present']
    json.dumps(trace, allow_nan=False)


def test_long_traces_are_bounded_with_actual_rul_and_no_interpolation(deep_app):
    _, original = deep_app
    bundle = enriched(original)
    clean, faulted = bundle.replay_series
    clean.failure_cycle = faulted.failure_cycle = 200
    clean.points = [ReplayPoint(cycle=c, rul=200-c, score=.7 if c % 4 else .2, alert=c % 3 == 0) for c in range(1, 201)]
    faulted.points = [point.model_copy(deep=True, update={'score': .4}) for point in clean.points]
    clean.threshold = faulted.threshold = .5
    trace = matched_trace(clean, faulted, bundle.development_selection.criteria)
    assert trace['sampled_points'] <= MAX_TRACE_POINTS
    assert trace['total_recorded_points'] == 200 and trace['omitted_points'] > 0
    assert trace['useful_window_complete']
    assert all(p['clean_score'] == clean.points[200-p['rul']-1].score for p in trace['points'])
    assert trace['points'] == sorted(trace['points'], key=lambda p: -p['rul'])


def test_missing_or_incompatible_trace_is_unavailable(deep_app):
    _, original = deep_app
    bundle = enriched(original)
    clean, faulted = bundle.replay_series
    for updates in ({'threshold': .99}, {'failure_cycle': 101}, {'partition': 'holdout'}, {'points': []}):
        assert matched_trace(clean.model_copy(update=updates), faulted, bundle.development_selection.criteria)['status'] == 'unavailable'


def test_ambiguous_faulted_versions_are_not_silently_selected(deep_app):
    _, original = deep_app
    bundle = enriched(original)
    duplicate = bundle.replay_series[1].model_copy(deep=True)
    duplicate.points[0].score += .1
    bundle.replay_series.append(duplicate)
    _, packet, _, _ = packet_for(bundle)
    assert packet['supporting_evidence']['paired_histories']['items'] == []


def test_packet_contains_citable_aligned_excerpt_and_unchanged_evidence(deep_app):
    _, original = deep_app
    bundle = enriched(original)
    before = bundle.model_dump_json()
    observations, packet, _, _ = packet_for(bundle)
    pair = packet['supporting_evidence']['paired_histories']['items'][0]
    assert pair['score_warning_trace']['status'] == 'available'
    assert any('Scores cross thresholds' in o.text for o in observations if o.id == pair['observation_id'])
    assert len(json.dumps(packet['supporting_evidence']).encode()) <= 14000
    assert bundle.model_dump_json() == before


def test_real_benchmark_pairs_survive_budget_and_do_not_guess_other_histories():
    from pathlib import Path
    from app.assistant.deep import collect_deep_evidence
    from app.assistant.investigation import EvidenceTools
    from app.assistant.schemas import AnalysisRequest
    from app.evidence.bundle import load_bundle
    from app.evidence.supplement import attach_replays
    path = Path(__file__).resolve().parents[1] / 'evidence/bundle.json'
    bundle = load_bundle(path)
    attach_replays(bundle, path)
    before = bundle.model_dump_json()
    _, packet, _, _ = collect_deep_evidence(EvidenceTools(bundle, AnalysisRequest(task='deep', candidates=['xgboost_augmented/aug3', 'logistic_regression/lr2'])))
    support = packet['supporting_evidence']
    pairs = support['paired_histories']['items']
    assert {row['model'] for row in pairs} == {'model-1', 'model-2'}
    assert all(row['score_warning_trace']['status'] == 'available' for row in pairs)
    assert len(json.dumps(support).encode()) <= 14000
    assert all(row['score_warning_trace']['sampled_points'] <= MAX_TRACE_POINTS for row in pairs)
    assert bundle.model_dump_json() == before


def test_excerpt_citation_survives_reuse_brief_and_export_without_another_request(deep_app, monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import routes_assistant
    from test_deep_investigation import BODY, HEADERS, completed, fake_provider
    app, original = deep_app
    loaded = enriched(original)
    monkeypatch.setattr(routes_assistant, 'bundle', lambda *_: loaded)
    app.state.assistant.allow_workspace()
    def cite(output):
        output['hypotheses'][0]['observation_ids'] = ['pattern-1', 'history-summary-1']
        output['next_tests'][0]['observation_ids'] = ['pattern-1', 'history-summary-1']
    calls = fake_provider(monkeypatch, cite)
    body = {**BODY, 'candidates': ['logistic_regression/lr2']}
    with TestClient(app) as client:
        start = client.post('/api/assistant/analyses', headers=HEADERS, json=body).json()
        record = completed(client, start['id'])
        report = record['result']['deep_report']
        assert report, record['result']['fallback_reason']
        observation = next(row for row in report['observations'] if row['id'] == 'history-summary-1')
        assert observation['summary'] and 'Scores cross thresholds' in observation['text']
        source = next(s for s in record['result']['sources'] if s['id'] in observation['source_ids'])
        assert json.loads(source['value'])['score_warning_trace']['status'] == 'available'
        assert 'missing useful-window cycles' in ' '.join(report['next_tests'][0]['prerequisites'])
        reopened = client.post('/api/assistant/analyses?reuse=true', headers=HEADERS, json=body).json()
        assert reopened['id'] == start['id']
        brief = client.post(f"/api/assistant/analyses/{start['id']}/review", headers=HEADERS).json()
        assert brief['result']['deep_report'] == report
        assert 'Scores cross thresholds' in brief['result']['brief_draft']
    assert len(calls) == 1
