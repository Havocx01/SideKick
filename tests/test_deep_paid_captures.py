"""Exact paid outputs are immutable regressions, not newly invented successes."""
import json
from pathlib import Path

import pytest

from test_deep_evaluation import evaluator
from test_deep_investigation import deep_app as deep_app


def replay(name):
    module = evaluator()
    bundle = module.load_bundle(module.ROOT / 'evidence/bundle.json')
    module.attach_replays(bundle, module.ROOT / 'evidence/bundle.json')
    capture = json.loads((Path(__file__).parent / 'fixtures' / name).read_text(encoding='utf-8'))
    return module.replay_capture(capture, bundle)


def test_exact_final_paid_passing_answer_keeps_scoped_explanation_and_timing_check():
    report, partial = replay('deep_paid_passing_final_20261012.json')
    assert not partial and len(report.hypotheses) == len(report.next_tests) == 1
    item = report.hypotheses[0]
    assert item.title == 'Possible score-response changes with retained warnings'
    assert item.observation_ids == ['pattern-2', 'history-summary-1']
    assert 'If fault-induced signal drift' in item.explanation
    check = report.next_tests[0]
    assert 'warning lead changes without warning loss' in check.focus
    assert 'Both cited histories retain warnings' in check.procedure
    assert 'later than the clean history' in check.expected_signal
    assert 'prior warning state' in check.interpretation


@pytest.mark.parametrize('name', ['deep_paid_failing_20261012.json', 'deep_paid_comparison_20261012.json'])
def test_exact_failing_comparison_keep_questions_without_contradictory_explanations(name):
    report, partial = replay(name)
    assert partial and report.hypotheses == [] and len(report.next_tests) == 1
    assert report.next_tests[0].check_type == 'score_persistence'
    assert 'fitted preprocessing' in ' '.join(report.next_tests[0].prerequisites)


def test_initial_passing_paid_question_cannot_claim_below_threshold_without_warning():
    # Fresh admission rejects this old question; stored historical output is not deleted.
    with pytest.raises(ValueError):
        replay('deep_paid_passing_initial_20261012.json')


def test_final_paid_answer_survives_api_refresh_reuse_brief_save_and_export(deep_app, monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import routes_assistant
    from app.evidence.supplement import attach_replays
    from test_deep_investigation import HEADERS, completed, fake_provider
    app, bundle = deep_app
    attach_replays(bundle, Path(__file__).resolve().parents[1] / 'evidence/bundle.json')
    monkeypatch.setattr(routes_assistant, 'bundle', lambda *_: bundle)
    app.state.assistant.store.set_workspace_consent(True)
    capture = json.loads((Path(__file__).parent / 'fixtures/deep_paid_passing_final_20261012.json').read_text())
    def answer(output):
        output.clear()
        output.update(capture['parsed'])
    calls = fake_provider(monkeypatch, answer)
    body = capture['context']
    with TestClient(app) as client:
        start = client.post('/api/assistant/analyses', headers=HEADERS, json=body).json()
        record = completed(client, start['id'])
        report = record['result']['deep_report']
        assert report['explanation_status'] == 'retained' and len(report['hypotheses']) == 1
        assert record['result']['fallback_reason'] is None
        assert client.get('/api/assistant/analyses/' + start['id']).json()['output_currency'] == 'current'
        assert client.post('/api/assistant/analyses?reuse=true', headers=HEADERS, json=body).json()['id'] == start['id']
        path = '/api/assistant/analyses/' + start['id']
        brief = client.post(path + '/review', headers=HEADERS).json()
        assert brief['result']['deep_report'] == report
        assert client.post(path + '/brief', headers=HEADERS, json={'text': brief['result']['brief_draft']}).status_code == 200
        assert client.get(path + '/export').status_code == 200
    assert len(calls) == 1
