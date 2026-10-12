"""Added-value reporting must not confuse format acceptance with engineer benefit."""
import argparse
import asyncio
import importlib.util
import json
from pathlib import Path

import pytest


def evaluator():
    path = Path(__file__).resolve().parents[1] / 'scripts/evaluate_deep.py'
    spec = importlib.util.spec_from_file_location('deep_evaluator', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_paid_ceiling_counts_failures_and_blocks_duplicate_cases():
    from app.assistant.deep import provider_synthesis_schema
    module = evaluator()
    params = {'model': module.MODEL, 'input': [], 'max_output_tokens': 2800,
              'text_format': provider_synthesis_schema(['pattern-1'])}
    ledger = {}
    module.admit(ledger, 'failing', params)
    with pytest.raises(RuntimeError):
        module.admit(ledger, 'failing', params)
    module.admit(ledger, 'comparison', params)
    with pytest.raises(RuntimeError):
        module.admit(ledger, 'passing', params)
    assert len(ledger['calls']) == 2
    with pytest.raises(RuntimeError):
        module.admit({}, 'failing', {**params, 'model': 'another-model'})
    with pytest.raises(RuntimeError):
        module.admit({}, 'failing', {**params, 'input': [{'content': 'x'*300000}]})


def test_explicit_campaign_budget_counts_all_attempts_and_rejects_fifth():
    from app.assistant.deep import provider_synthesis_schema
    module = evaluator()
    params = {'model': module.MODEL, 'input': [], 'max_output_tokens': 2800,
              'text_format': provider_synthesis_schema(['pattern-1'])}
    ledger = {'max_requests': 4, 'max_usd': .10, 'calls': []}
    for label in ['passing:initial', 'failing:initial', 'comparison:initial', 'passing:after-fix']:
        module.admit(ledger, label, params)
    with pytest.raises(RuntimeError):
        module.admit(ledger, 'comparison:after-fix', params)
    with pytest.raises(RuntimeError):
        module.admit({'max_requests': 5}, 'passing:initial', params)
    assert len(ledger['calls']) == 4
    with pytest.raises(ValueError):
        module.campaign_folder(argparse.Namespace(campaign='../escape'))


def test_offline_comparison_has_no_provider_and_no_invented_human_times(tmp_path, monkeypatch):
    module = evaluator()
    def forbidden(**_):
        raise AssertionError('Offline evaluation created a network client')
    monkeypatch.setattr(module.deep, 'AsyncOpenAI', forbidden)
    folder = tmp_path/'evaluation'
    args = argparse.Namespace(output=folder, case=None, live=False, capture=None)
    assert asyncio.run(module.run(args)) == 0
    report = json.loads((folder/'results.json').read_text(encoding='utf-8'))
    assert report['paid_requests'] == 0 and report['evidence_unchanged']
    assert not report['engineer_study_conducted'] and not report['human_decision_times_measured']
    assert {'failing', 'passing', 'comparison', 'missing-evidence'} <= {r['case'] for r in report['cases']}
    assert all(r['added_value']['engineer_next_check_better'] is None and r['added_value']['engineer_decision_seconds'] is None for r in report['cases'])
    scores = (folder/'review/score-sheet.csv').read_text(encoding='utf-8')
    assert 'review_seconds' in scores and 'generation_wait_seconds' in scores
    with pytest.raises(ValueError):
        asyncio.run(module.run(args))


def test_older_generic_trace_explanations_fail_new_admission_but_keep_safe_questions():
    module = evaluator()
    bundle = module.load_bundle(module.ROOT/'evidence/bundle.json')
    module.attach_replays(bundle, module.ROOT/'evidence/bundle.json')
    paths = sorted((module.ROOT/'tests/fixtures').glob('deep_traces_*_20261011.json'))
    assert len(paths) == 2
    for path in paths:
        capture = json.loads(path.read_text(encoding='utf-8'))
        synthesis, partial = module.replay_capture(capture, bundle)
        # Immutable v18 captures did not select a trace basis. Do not credit them
        # with the current trace-specific contract or rewrite the originals.
        assert capture['prompt'] == 'sidekick-deep-v18'
        assert partial and synthesis.hypotheses == []
        assert synthesis.next_tests
