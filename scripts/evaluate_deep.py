"""Compare regular analysis with exact saved deep answers; offline by default.

--live --case failing --case comparison admits at most two requests in a durable
ledger, no retries, with the current model and a conservative $0.10 ceiling.
An explicitly named campaign may reserve up to four total requests; failed calls
count and its limits cannot be increased. Each invocation selects at most two cases.
Generation latency is measured; engineer decision time is deliberately left blank.
No experiment, consent, training, validation or user-draft records are changed.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import html
import io
import json
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.assistant import deep
from app.assistant.diagnostic_checks import compose_checks
from app.assistant.investigation import EvidenceTools
from app.assistant.schemas import AnalysisRequest
from app.config import get_settings
from app.evidence.bundle import load_bundle
from app.evidence.supplement import attach_replays

MAX_REQUESTS = 2
MAX_USD = .10
MODEL = 'gpt-4.1-mini-2025-04-14'
CASES = {'failing': ['logistic_regression/lr2'], 'passing': ['xgboost_augmented/aug3'],
    'comparison': ['xgboost_augmented/aug3', 'logistic_regression/lr2'],
    'missing-evidence': ['logistic_regression/lr2']}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as target:
        target.write(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
        temporary = Path(target.name)
    temporary.replace(path)


def admit(ledger, label, params):
    """Reserve before network dispatch. Failed calls consume a slot and reservation."""
    from openai.lib._parsing._responses import type_to_text_format_param
    schema = type_to_text_format_param(params['text_format'])
    byte_bound = len(json.dumps(params['input']).encode()) + len(json.dumps(schema).encode()) + 2000
    cost = (byte_bound * .4 + params['max_output_tokens'] * 1.6) / 1_000_000
    calls = ledger.setdefault('calls', [])
    request_limit = ledger.get('max_requests', MAX_REQUESTS)
    cost_limit = ledger.get('max_usd', MAX_USD)
    if type(request_limit) is not int or not 1 <= request_limit <= 4 or not 0 < cost_limit <= MAX_USD:
        raise RuntimeError('Invalid paid evaluation limits.')
    if params['model'] != MODEL or len(calls) >= request_limit or any(c['case'] == label for c in calls) or sum(c.get('cost_usd', c['reserved_usd']) for c in calls) + cost > cost_limit:
        raise RuntimeError('Paid request, model, duplicate-case or cost limit reached.')
    row = {'case': label, 'model': params['model'], 'prompt': deep.PROMPT_VERSION, 'reserved_usd': cost, 'status': 'admitted'}
    calls.append(row)
    return row


def local_answer(bundle, context):
    start = time.perf_counter()
    regular = context.model_copy(update={'task': 'compare' if len(context.candidates) == 2 else 'investigate',
        'engineer_context': None, 'investigation_focus': None})
    result = EvidenceTools(bundle, regular).local()
    return result, time.perf_counter()-start


def added_value(local, report):
    """Observable differences, never an automatic certificate of engineering value."""
    check = report.next_tests[0] if report else None
    return {'retained_explanations': len(report.hypotheses) if report else 0,
        'distinguishing_question': check.focus if check else None,
        'check_type': check.check_type if check else None,
        'conditional_outcomes': check.interpretation if check else None,
        'missing_prerequisites': check.prerequisites if check else [],
        'regular_next_check': local.actions[0].detail if local.actions else None,
        'question_differs_from_regular': bool(check and check.focus and all(check.focus != a.detail for a in local.actions)),
        'engineer_next_check_better': None, 'engineer_decision_seconds': None,
        'verdict': 'Needs engineer comparison; changed wording and server-owned diagnostic branches are not proof of AI added value.' if check else 'No retained AI-specific check; regular analysis remains available.'}


def replay_capture(capture, bundle):
    """Keep the original packet; new traces cannot be credited to an old answer."""
    context = AnalysisRequest.model_validate(capture['context'])
    tools = EvidenceTools(bundle, context)
    observations, current, aliases, _ = deep.collect_deep_evidence(tools)
    packet = capture['packet']
    if packet['observations'] != current['observations']:
        raise ValueError('Saved answer pattern scope no longer matches the recorded case.')
    allowed = {row['id'] for row in packet['observations']} | {row['observation_id']
        for section in packet.get('supporting_evidence', {}).values() for row in section.get('items', [])}
    observations = [row for row in observations if row.id in allowed]
    if 'check_type' in capture['parsed']['next_tests'][0]:
        schema = deep.provider_synthesis_schema([row.id for row in observations], packet=packet)
        synthesis, partial = compose_checks(schema.model_validate(capture['parsed']), packet, observations, aliases)
    else:
        # Historical format review only. Production does not admit this legacy
        # provider schema. Do not pretend this is a new-generation success.
        schema = deep.provider_synthesis_schema([row.id for row in observations])
        synthesis, partial = deep.verified_synthesis(schema.model_validate(capture['parsed']), observations, aliases,
            fault_kinds={row['kind'] for row in packet['observations']})
    return synthesis, partial


def packet_facts(packet):
    """Human-readable facts from the original input, never later supporting records."""
    lines = [f"Partition: {packet['partition']}. Required simulated fault patterns; selected examples are not population evidence."]
    for pattern in packet['observations']:
        lines.append(f"{pattern['id']} · {pattern['model']} · {pattern['channel']} · {pattern['kind']} · {pattern['duration']}: "
            f"{pattern['cases']} cases; {pattern['failed_cases']} outside limits; timely detection {pattern['minimum_detection']:.2%}–{pattern['maximum_detection']:.2%}; coverage {pattern['coverage']}.")
    for pair in packet.get('supporting_evidence', {}).get('paired_histories', {}).get('items', []):
        window = pair['faulted']['useful_window']
        lines.append(f"{pair['observation_id']} · {pair['model']} · {pair['history']} · related {', '.join(pair['related_pattern_ids'])}: "
            f"clean {pair['clean']['outcome']} → faulted {pair['faulted']['outcome']}; own threshold {pair['threshold']:.6g}; "
            f"{window['above_threshold']} useful-window scores at/above threshold, {window['active_cycles']} active-warning cycles.")
    return lines


def review_pack(rows, folder):
    """A/B labels rotate; method key is facilitator-only, times remain unobserved."""
    pages, key = [], []
    sheet = io.StringIO(newline='')
    writer = csv.writer(sheet)
    writer.writerow(['reviewer', 'case', 'answer_label', 'decision', 'reason', 'next_check', 'next_check_quality_0_2',
        'critical_scope_errors', 'review_seconds', 'generation_wait_seconds', 'edits_needed', 'usefulness_reason'])
    for index, row in enumerate(rows):
        local = row['local']
        regular = '\n'.join([local['summary'], *[c['text'] for c in local['assessment']],
            *[a['detail'] for a in local['actions'][:1]]])
        report = row.get('report')
        ai = regular
        if report:
            ai += '\n\nPossible explanations — need checking\n' + '\n'.join(
                f"{h['title']}: {h['explanation']} Alternative: {h['alternative']}" for h in report['hypotheses'])
            ai += '\n\nProposed checks\n' + '\n'.join(
                ' '.join(str(c.get(k) or '') for k in ('focus', 'procedure', 'expected_signal', 'interpretation')) +
                ' Prerequisites: ' + '; '.join(c.get('prerequisites', [])) for c in report['next_tests'])
        methods = [('regular', regular), ('ai_assisted' if report else 'safe_fallback', ai)]
        if index % 2:
            methods.reverse()
        facts = '\n'.join(packet_facts(row['packet']))
        pages.append(f"<section><h2>{html.escape(row['case'])}</h2><p>Choose a justified next check. Explain its evidence, controls and uncertainty.</p><details><summary>Common recorded evidence (same for both answers)</summary><pre>{html.escape(facts)}</pre></details>")
        for label, (method, answer) in zip(('A', 'B'), methods, strict=True):
            pages.append(f'<h3>Answer {label}</h3><pre>{html.escape(answer)}</pre>')
            writer.writerow(['', row['case'], label] + ['']*9)
            key.append({'case': row['case'], 'label': label, 'method': method, 'capture_prompt': row.get('capture_prompt'),
                'generation_seconds': row.get('generation_seconds'), 'historical': row.get('historical', False)})
        pages.append('</section>')
    folder.mkdir(parents=True, exist_ok=True)
    # Do not overwrite reviewer annotations or a previous pack.
    with (folder/'review.html').open('x', encoding='utf-8') as target:
        target.write('<!doctype html><html lang="en"><meta charset="utf-8"><title>Sidekick analysis comparison</title><style>body{max-width:900px;margin:32px auto;padding:20px;font:16px/1.5 system-ui}pre{white-space:pre-wrap;overflow-wrap:anywhere}section{border-top:1px solid #bbb;margin-top:32px}</style><h1>Analysis comparison</h1><p>No engineer study has been conducted. Use independent reviewers or equivalent cases to avoid learning effects. Score correctness before speed; record waiting time separately. A fallback is not successful AI.</p>' + ''.join(pages) + '</html>')
    with (folder/'score-sheet.csv').open('x', encoding='utf-8', newline='') as target:
        target.write(sheet.getvalue())
    write(folder/'facilitator-key.json', key)


async def run(args):
    if args.output.exists():
        raise ValueError('Choose a new output directory; existing results and reviewer notes are retained.')
    path = ROOT/'evidence/bundle.json'
    bundle = load_bundle(path)
    attach_replays(bundle, path)
    before = bundle.model_dump_json()
    rows = []
    selected = args.case or list(CASES)
    if args.live and (not args.case or len(selected) > MAX_REQUESTS or len(set(selected)) != len(selected)):
        raise ValueError('Explicitly select one or two unique cases for live evaluation.')
    from dotenv import load_dotenv
    if args.live:
        load_dotenv(ROOT/'.env', override=False)
    settings = get_settings()
    if args.live and (not settings.openai_api_key or settings.assistant_model != MODEL):
        raise ValueError('Current configured model and server key required; no request admitted.')
    ledger_path = campaign_folder(args)/'paid-ledger.json'
    requested_limit = getattr(args, 'max_requests', MAX_REQUESTS)
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {'max_requests': requested_limit, 'max_usd': MAX_USD, 'calls': []}
    if args.live and ledger.get('max_requests', MAX_REQUESTS) != requested_limit:
        raise ValueError('Existing campaign limits cannot be changed; retain the original budget.')
    attempt = getattr(args, 'attempt', 'initial')
    for name in selected:
        scoped = bundle.model_copy(deep=True)
        if name == 'missing-evidence':
            scoped.replay_series = []  # Explicit offline missing-record fixture, not a historical inference.
        context = AnalysisRequest(task='deep', candidates=CASES[name])
        local, local_seconds = local_answer(scoped, context)
        tools = EvidenceTools(scoped, context)
        obs, packet, _, _ = deep.collect_deep_evidence(tools)
        row = {'case': name, 'context': context.model_dump(mode='json'), 'local': local.model_dump(mode='json'),
            'local_seconds': local_seconds, 'recorded_facts': [o.summary for o in obs if o.summary],
            'packet': packet, 'paid_requests': 0, 'report': None, 'status': 'offline_baseline'}
        if args.live:
            original = deep.AsyncOpenAI
            calls = []
            def metered(**kwargs):
                if kwargs.get('max_retries') != 0:
                    raise RuntimeError('Provider retries are prohibited.')
                sdk = original(**kwargs)
                class Responses:
                    async def parse(self, **params):
                        admission = admit(ledger, name + ':' + attempt, params)
                        calls.append(admission)
                        write(ledger_path, ledger)
                        try:
                            response = await sdk.responses.parse(**params)
                            usage = response.usage
                            admission.update(status='returned', cost_usd=(usage.input_tokens*.4+usage.output_tokens*1.6)/1_000_000,
                                input_tokens=usage.input_tokens, output_tokens=usage.output_tokens)
                            capture = {'context': context.model_dump(mode='json'), 'prompt': deep.PROMPT_VERSION,
                                'packet': json.loads(params['input'][-1]['content']), 'parsed': response.output_parsed.model_dump() if response.output_parsed else None,
                                'usage': usage.model_dump()}
                            write(args.output/f'{name}-capture.json', capture)
                            return response
                        finally:
                            write(ledger_path, ledger)
                class Client:
                    responses = Responses()
                    async def __aenter__(self):
                        await sdk.__aenter__()
                        return self
                    async def __aexit__(self, *values):
                        return await sdk.__aexit__(*values)
                return Client()
            start = time.perf_counter()
            deep.AsyncOpenAI = metered
            try:
                enhanced = await deep.investigate_deep(tools, settings)
                row.update(report=enhanced.deep_report.model_dump(mode='json'), status='retained', capture_prompt=deep.PROMPT_VERSION)
                row['checks'] = {'server_findings_unchanged': enhanced.findings == tools.result.findings,
                    'server_summary_unchanged': enhanced.summary == tools.result.summary,
                    'source_scope_correct': all(s.partition == context.partition and s.candidate in context.candidates for s in enhanced.sources),
                    'citations_resolve': all(set(h.observation_ids) <= {o.id for o in enhanced.deep_report.observations} for h in [*enhanced.deep_report.hypotheses, *enhanced.deep_report.next_tests])}
                assert all(row['checks'].values())
            except Exception as error:
                row.update(report=None, status='safe_fallback', failure=error.reason if isinstance(error, deep.DeepVerificationError) else type(error).__name__)
            finally:
                deep.AsyncOpenAI = original
                row.update(generation_seconds=time.perf_counter()-start, paid_requests=len(calls))
                row['estimated_cost_usd'] = sum(call.get('cost_usd', call['reserved_usd']) for call in calls)
        report = SimpleNamespace(**row['report']) if row['report'] else None
        if report:
            report.next_tests = [SimpleNamespace(**c) for c in report.next_tests]
        row['added_value'] = added_value(local, report)
        rows.append(row)
    captures = args.capture or [ROOT/'tests/fixtures/deep_evaluation_history_20261011.json', *sorted((ROOT/'tests/fixtures').glob('deep_traces_*_20261011.json'))]
    for path in captures:
        loaded = json.loads(path.read_text(encoding='utf-8'))
        for capture in loaded if isinstance(loaded, list) else [loaded]:
            context = AnalysisRequest.model_validate(capture['context'])
            local, seconds = local_answer(bundle, context)
            synthesis = None
            try:
                synthesis, partial = replay_capture(capture, bundle)
                status, failure = 'partial' if partial else 'retained', None
            except ValueError as error:
                status, failure = 'safe_fallback', error.reason if isinstance(error, deep.DeepVerificationError) else type(error).__name__
            rows.append({'case': capture.get('case', path.stem), 'historical': capture['prompt'] != deep.PROMPT_VERSION,
                'contract_review': 'current' if 'check_type' in capture['parsed']['next_tests'][0] else 'legacy_only_not_production_admission',
                'capture_prompt': capture['prompt'], 'packet': capture['packet'], 'status': status, 'failure': failure,
                'report': synthesis.model_dump(mode='json') if synthesis else None, 'local': local.model_dump(mode='json'),
                'local_seconds': seconds, 'generation_seconds': capture.get('generation_seconds'), 'paid_requests': 0,
                'added_value': added_value(local, synthesis)})
    assert bundle.model_dump_json() == before
    artifact = {'prompt': deep.PROMPT_VERSION, 'engineer_study_conducted': False, 'human_decision_times_measured': False,
        'paid_requests': sum(r['paid_requests'] for r in rows), 'evidence_unchanged': True,
        'bundle_sha256': hashlib.sha256((ROOT/'evidence/bundle.json').read_bytes()).hexdigest(),
        'limitations': ['Selected benchmark debugging cases are not independent or representative field samples.',
            'Historical replay is not current-prompt generation. Retention and changed text do not establish usefulness.',
            'Procedures, controls and conditional branches are server-owned; do not credit them as AI-created value.'], 'cases': rows}
    write(args.output/'results.json', artifact)
    review_pack(rows, args.output/'review')
    print(json.dumps({'paid_requests': artifact['paid_requests'], 'evidence_unchanged': True,
        'cases': [{'case': r['case'], 'status': r['status'], 'explanations': r['added_value']['retained_explanations']} for r in rows]}, indent=2))
    return 0


def campaign_folder(args):
    campaign = getattr(args, 'campaign', None)
    if campaign is None:
        return ROOT/'output/matched-traces-20261011'
    import re
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', campaign):
        raise ValueError('Campaign must be a short lowercase name.')
    return ROOT/'output/deep-evaluations'/campaign


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--case', action='append', choices=CASES)
    parser.add_argument('--capture', action='append', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--campaign', help='Separate durable paid ledger for this explicitly authorized evaluation.')
    parser.add_argument('--max-requests', type=int, choices=range(1, 5), default=MAX_REQUESTS)
    parser.add_argument('--attempt', choices=('initial', 'after-fix'), default='initial')
    args = parser.parse_args()
    if not args.live:
        return asyncio.run(run(args))
    lock = campaign_folder(args)/'paid-evaluation.lock'
    lock.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents overlapping invocations from racing the ledger.
    # A crashed process leaves the lock in place for deliberate operator recovery.
    with lock.open('x', encoding='utf-8') as guard:
        guard.write('Exclusive live evaluation; remove only after confirming no evaluator is running.\n')
    try:
        return asyncio.run(run(args))
    finally:
        lock.unlink()


if __name__ == '__main__':
    raise SystemExit(main())
