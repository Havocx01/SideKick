"""Added-value reporting must not confuse format acceptance with engineer benefit."""
import argparse
import asyncio
import importlib.util
import json
from pathlib import Path

import pytest
import httpx


def evaluator():
    path = Path(__file__).resolve().parents[1] / 'scripts/evaluate_deep.py'
    spec = importlib.util.spec_from_file_location('deep_evaluator', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_paid_ceiling_counts_failures_and_blocks_duplicate_cases():
    from app.assistant.deep import provider_synthesis_schema
    module = evaluator()
    from app.assistant.transport import strict_schema
    params = {'model': module.MODEL, 'messages': [], 'max_tokens': 2800,
              'response_format': {'type': 'json_schema', 'json_schema': {'schema': strict_schema(provider_synthesis_schema(['pattern-1']))}}}
    rates = {'input_usd_per_million': .4, 'output_usd_per_million': 1.6}
    ledger = dict(rates)
    module.admit(ledger, 'failing', params)
    with pytest.raises(RuntimeError):
        module.admit(ledger, 'failing', params)
    module.admit(ledger, 'comparison', params)
    with pytest.raises(RuntimeError):
        module.admit(ledger, 'passing', params)
    assert len(ledger['calls']) == 2
    with pytest.raises(RuntimeError):
        module.admit(dict(rates), 'failing', {**params, 'model': 'another-model'})
    with pytest.raises(RuntimeError):
        module.admit(dict(rates), 'failing', {**params, 'messages': [{'content': 'x'*300000}]})
    with pytest.raises(RuntimeError, match='token prices'):
        module.admit({}, 'failing', params)


def test_explicit_campaign_budget_counts_all_attempts_and_rejects_fifth():
    from app.assistant.deep import provider_synthesis_schema
    module = evaluator()
    from app.assistant.transport import strict_schema
    params = {'model': module.MODEL, 'messages': [], 'max_tokens': 2800,
              'response_format': {'type': 'json_schema', 'json_schema': {'schema': strict_schema(provider_synthesis_schema(['pattern-1']))}}}
    ledger = {'max_requests': 4, 'max_usd': .10, 'calls': [], 'input_usd_per_million': .4, 'output_usd_per_million': 1.6}
    for label in ['passing:initial', 'failing:initial', 'comparison:initial', 'passing:after-fix']:
        module.admit(ledger, label, params)
    with pytest.raises(RuntimeError):
        module.admit(ledger, 'comparison:after-fix', params)
    with pytest.raises(RuntimeError):
        module.admit({**ledger, 'max_requests': 5}, 'passing:initial', params)
    assert len(ledger['calls']) == 4
    with pytest.raises(ValueError):
        module.campaign_folder(argparse.Namespace(campaign='../escape'))


@pytest.mark.parametrize('price', [None, 0, -1, float('inf'), float('nan')])
def test_invalid_token_prices_never_admit_a_request(price):
    module = evaluator()
    ledger = {'input_usd_per_million': price, 'output_usd_per_million': 1}
    with pytest.raises(RuntimeError, match='token prices'):
        module.admit(ledger, 'failing', {'model': module.MODEL, 'messages': [], 'max_tokens': 100})
    assert not ledger.get('calls')


def test_metered_nebius_evaluation_uses_chat_and_saves_usage_offline(tmp_path, monkeypatch):
    import dotenv
    from openai import AsyncOpenAI
    from app.config import Settings
    from test_deep_investigation import checked_fixture, provider_synthesis
    from test_nebius_provider import completion
    module = evaluator()
    monkeypatch.setattr(dotenv, 'load_dotenv', lambda *_args, **_kwargs: False)
    requests = []
    def respond(request):
        assert request.url.host == 'api.tokenfactory.nebius.com' and request.url.path == '/v1/chat/completions'
        payload = json.loads(request.content)
        requests.append(payload)
        packet = json.loads(payload['messages'][-1]['content'])
        output = checked_fixture(provider_synthesis([row['id'] for row in packet['observations']]), packet)
        body = completion(json.dumps(output))
        body['usage'] = {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150}
        return httpx.Response(200, json=body)
    def client(**kwargs):
        return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(module.deep, 'AsyncOpenAI', client)
    monkeypatch.setattr(module, 'get_settings', lambda: Settings(assistant_provider='nebius', nebius_api_key='mock-only',
        assistant_model=module.MODEL, assistant_timeout_seconds=10))
    monkeypatch.setattr(module, 'campaign_folder', lambda _: tmp_path/'campaign')
    args = argparse.Namespace(output=tmp_path/'evaluation', case=['failing'], live=True, capture=None, max_requests=2,
        attempt='initial', input_usd_per_million=1, output_usd_per_million=2)
    assert asyncio.run(module.run(args)) == 0
    ledger = json.loads((tmp_path/'campaign/paid-ledger.json').read_text())
    assert len(requests) == 1 and requests[0]['max_tokens'] > 4096
    assert ledger['calls'][0]['status'] == 'returned' and ledger['calls'][0]['cost_usd'] == .0002
    capture = json.loads((args.output/'failing-capture.json').read_text())
    assert capture['parsed'] and capture['usage']['completion_tokens'] == 50


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
