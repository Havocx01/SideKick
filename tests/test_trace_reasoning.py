"""Trace-specific explanations, not aggregate-only speculation or causal titles."""
import json
from pathlib import Path

import pytest

from app.assistant.deep import collect_deep_evidence, provider_synthesis_schema
from app.assistant.diagnostic_checks import compose_checks
from app.assistant.investigation import EvidenceTools
from app.assistant.schemas import AnalysisRequest
from app.config import get_settings
from app.evidence.bundle import load_bundle
from test_deep_investigation import deep_app as deep_app


def captured():
    capture = json.loads((Path(__file__).parent / 'fixtures/deep_traces_failing_20261011.json').read_text())
    tools = EvidenceTools(load_bundle(get_settings().bundle_path), AnalysisRequest.model_validate(capture['context']))
    observations, _, aliases, _ = collect_deep_evidence(tools)
    # Sources are not needed for composition; capture retains the exact immutable packet.
    from app.assistant.schemas import DeepObservation
    for row in capture['packet']['supporting_evidence']['paired_histories']['items']:
        observations.append(DeepObservation(id=row['observation_id'], title='Matched history',
            text='Selected recorded history.', source_ids=[]))
    return capture['packet'], observations, aliases, capture['parsed']


def compose(packet, observations, aliases, output):
    schema = provider_synthesis_schema([row.id for row in observations], packet=packet)
    return compose_checks(schema.model_validate(output), packet, observations, aliases)


def specific(output):
    output['hypotheses'] = [{
        'title': 'Weak scores causing missed warnings',
        'trace_basis': 'short_crossings',
        'explanation': 'Faulted scores may cross only briefly because input changes destabilize the score response in this selected history.',
        'alternative': 'The selected threshold could instead leave crossing streaks too short to satisfy the recorded opening rule.',
        'observation_ids': ['pattern-1', 'history-summary-1'],
    }]
    output['next_tests'][0]['observation_ids'] = ['pattern-1', 'history-summary-1']
    return output


def test_actual_trace_choices_distinguish_absent_and_short_crossings():
    from app.assistant.trace_reasoning import trace_options
    packet, _, _, _ = captured()
    options = trace_options(packet)
    assert options['history-summary-1'] == 'short_crossings'
    assert options['history-summary-2'] == 'no_useful_crossings'
    pair = packet['supporting_evidence']['paired_histories']['items'][0]
    pair['score_warning_trace']['useful_window_complete'] = False
    assert 'history-summary-1' not in trace_options(packet)


def test_trace_specific_explanation_keeps_tentative_server_title_and_exact_citations():
    packet, observations, aliases, output = captured()
    report, partial = compose(packet, observations, aliases, specific(output))
    assert not partial
    assert report.hypotheses[0].title == 'Possible reasons for short score-crossing streaks'
    assert report.hypotheses[0].observation_ids == ['pattern-1', 'history-summary-1']
    assert 'trace_basis' not in report.hypotheses[0].model_dump()
    assert 'causing' not in report.hypotheses[0].title


@pytest.mark.parametrize('change', ['missing_basis', 'missing_history', 'wrong_basis', 'generic', 'contradiction', 'other_pattern'])
def test_ungrounded_explanations_are_omitted_without_losing_safe_check(change):
    packet, observations, aliases, output = captured()
    output = specific(output)
    item = output['hypotheses'][0]
    if change == 'missing_basis':
        item.pop('trace_basis')
    elif change == 'missing_history':
        item['observation_ids'] = ['pattern-1']
    elif change == 'wrong_basis':
        item['trace_basis'] = 'no_useful_crossings'
    elif change == 'generic':
        item['explanation'] = 'The model may respond differently to substituted readings.'
    elif change == 'contradiction':
        item['explanation'] = 'All faulted scores could remain below the threshold in this selected history.'
    else:
        item['observation_ids'] = ['pattern-2', 'history-summary-1']
    report, partial = compose(packet, observations, aliases, output)
    assert partial and report.hypotheses == [] and report.next_tests


def test_no_crossings_cannot_be_explained_by_persistence_alone():
    packet, observations, aliases, output = captured()
    output = specific(output)
    item = output['hypotheses'][0]
    item.update(trace_basis='no_useful_crossings', observation_ids=['pattern-1', 'history-summary-2'],
        explanation='Faulted scores may remain below the selected threshold because their response to these inputs is weak.',
        alternative='Persistence alone could instead block the warning despite sustained score crossings.')
    report, partial = compose(packet, observations, aliases, output)
    assert partial and report.hypotheses == [] and report.next_tests


def test_incomplete_and_unknown_rules_do_not_get_whole_window_basis():
    from app.assistant.trace_reasoning import trace_options
    packet, _, _, _ = captured()
    packet['supporting_evidence']['paired_histories']['warning_rules']['alert_on_consecutive'] = None
    assert 'history-summary-1' not in trace_options(packet)
    pair = packet['supporting_evidence']['paired_histories']['items'][1]
    pair['faulted']['useful_window']['valid_scores'] -= 1
    assert 'history-summary-2' not in trace_options(packet)


def test_sustained_crossings_are_inspection_condition_not_logic_defect():
    from app.assistant.trace_reasoning import trace_options
    packet, observations, aliases, output = captured()
    pair = packet['supporting_evidence']['paired_histories']['items'][0]
    pair['score_warning_trace']['useful_maximum_high_streak']['faulted'] = 3
    pair['faulted']['useful_window']['above_threshold'] = 3
    assert trace_options(packet)['history-summary-1'] == 'sustained_crossings_without_warning'
    output = specific(output)
    output['hypotheses'][0].update(trace_basis='sustained_crossings_without_warning',
        explanation='Recorded activation timing could differ from the sustained crossing streaks in this selected history.',
        alternative='The useful-window alignment may instead omit relevant earlier warning-state context.')
    report, _ = compose(packet, observations, aliases, output)
    assert report.hypotheses[0].title == 'Possible timing or warning-state mismatch'
    assert 'defect' not in report.hypotheses[0].title


def test_no_crossings_retains_two_compatible_tentative_mechanisms():
    packet, observations, aliases, output = captured()
    output = specific(output)
    output['hypotheses'][0].update(trace_basis='no_useful_crossings',
        observation_ids=['pattern-1', 'history-summary-2'],
        explanation='Faulted scores may remain below their threshold because the model responds weakly to substituted inputs in this matched history.',
        alternative='Threshold placement could instead require a stronger score response than these inputs provide.')
    report, partial = compose(packet, observations, aliases, output)
    assert not partial and len(report.hypotheses) == 1


def test_unpublished_provider_title_cannot_override_safe_scoped_title():
    packet, observations, aliases, output = captured()
    output = specific(output)
    output['hypotheses'][0]['title'] = 'Model-2 definitely caused the physical failure'
    report, partial = compose(packet, observations, aliases, output)
    assert not partial
    assert report.hypotheses[0].title == 'Possible reasons for short score-crossing streaks'
    assert 'physical failure' not in report.model_dump_json()


def test_intermittent_crossings_allow_some_scores_to_remain_below_threshold():
    packet, observations, aliases, output = captured()
    output = specific(output)
    output['hypotheses'][0].update(
        explanation='Faulted scores might produce transient crossings because the model responds inconsistently in this matched history.',
        alternative='Threshold placement could instead leave most scores below the threshold between crossings.')
    report, partial = compose(packet, observations, aliases, output)
    assert not partial and report.hypotheses


def test_provider_schema_requires_nullable_basis_without_changing_public_report():
    from app.assistant.transport import strict_schema
    from app.assistant.schemas import DeepHypothesis
    packet, observations, _, _ = captured()
    schema = strict_schema(provider_synthesis_schema([row.id for row in observations], packet=packet))
    definition = schema['$defs']['ScopedDeepHypothesis']
    assert 'trace_basis' in definition['required']
    assert 'trace_basis' not in DeepHypothesis.model_json_schema()['properties']


def test_trace_basis_and_title_survive_mocked_reuse_brief_and_export(deep_app, monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import routes_assistant
    from app.assistant.deep import PROMPT_VERSION
    from app.evidence.supplement import attach_replays
    from test_deep_investigation import HEADERS, completed, fake_provider
    app, bundle = deep_app
    attach_replays(bundle, Path(__file__).resolve().parents[1] / 'evidence/bundle.json')
    before = bundle.model_dump_json()
    monkeypatch.setattr(routes_assistant, 'bundle', lambda *_: bundle)
    app.state.assistant.allow_workspace()
    def answer(output):
        _, _, _, capture = captured()
        output.clear()
        output.update(specific(capture))
    calls = fake_provider(monkeypatch, answer)
    body = {'task': 'deep', 'candidates': ['logistic_regression/lr2']}
    with TestClient(app) as client:
        start = client.post('/api/assistant/analyses', json=body, headers=HEADERS).json()
        saved = completed(client, start['id'])
        assert saved['result']['prompt_version'] == PROMPT_VERSION
        report = saved['result']['deep_report']
        assert report, saved['result']['fallback_reason']
        assert report['hypotheses'][0]['title'] == 'Possible reasons for short score-crossing streaks'
        assert report['hypotheses'][0]['observation_ids'] == ['pattern-1', 'history-summary-1']
        assert client.post('/api/assistant/analyses?reuse=true', json=body, headers=HEADERS).json()['id'] == start['id']
        path = '/api/assistant/analyses/' + start['id']
        brief = client.post(path + '/review', headers=HEADERS).json()
        assert brief['result']['deep_report'] == report
        assert report['hypotheses'][0]['title'] in brief['result']['brief_draft']
        assert client.post(path + '/brief', json={'text': brief['result']['brief_draft']}, headers=HEADERS).status_code == 200
        assert client.get(path + '/export').status_code == 200
    assert len(calls) == 1 and bundle.model_dump_json() == before
    packet = json.loads(calls[0]['messages'][-1]['content'])
    assert packet['diagnostic_contract']['trace_bases']['history-summary-1'] == 'short_crossings'


def test_passing_history_gets_retained_warning_basis_not_missing_warning():
    from app.assistant.trace_reasoning import trace_options, explanation_anchor
    packet, observations, aliases, output = captured()
    pair = packet['supporting_evidence']['paired_histories']['items'][0]
    pair['faulted']['useful_window'].update(active_cycles=19, above_threshold=19)
    pair['faulted']['outcome'] = 'timely'
    assert trace_options(packet)['history-summary-1'] == 'warning_retained'
    anchor = explanation_anchor(packet)
    assert anchor['observation_ids'] == ['pattern-1', 'history-summary-1']
    assert anchor['recommended_signal'] == 'crossings_without_warning'
    output = specific(output)
    output['hypotheses'][0].update(trace_basis='warning_retained',
        explanation='Faulted inputs could shift sustained score-crossing timing while warnings remain timely in this selected history.',
        alternative='Prior warning-state context may instead account for the change in activation timing.')
    output['next_tests'][0].update(signal='crossings_without_warning', focus='Inspect crossing timing and warning lead.')
    report, partial = compose(packet, observations, aliases, output)
    assert not partial
    assert report.hypotheses[0].title == 'Possible score-response changes with retained warnings'
    assert 'Both cited histories retain warnings' in report.next_tests[0].procedure
    assert 'reaches the recorded opening streak later' in report.next_tests[0].expected_signal


def test_known_cited_ids_in_prose_are_references_not_unsupported_numbers():
    packet, observations, aliases, output = captured()
    output = specific(output)
    output['next_tests'][0]['focus'] = 'Inspect crossing streaks in history-summary-1 for pattern-1.'
    report, partial = compose(packet, observations, aliases, output)
    assert not partial and report.next_tests
    output['next_tests'][0]['focus'] = 'Inspect crossing streaks in history-summary-999.'
    with pytest.raises(ValueError):
        compose(packet, observations, aliases, output)


def test_retained_faulted_warning_does_not_invent_a_clean_warning():
    packet, observations, aliases, output = captured()
    pair = packet['supporting_evidence']['paired_histories']['items'][0]
    pair['faulted']['useful_window'].update(active_cycles=19, above_threshold=19)
    pair['clean']['useful_window']['active_cycles'] = 0
    pair['clean']['outcome'] = 'missed'
    output['hypotheses'] = []
    output['next_tests'][0].update(observation_ids=['pattern-1', 'history-summary-1'],
        signal='crossings_without_warning', focus='Inspect crossing timing and warning lead.')
    report, _ = compose(packet, observations, aliases, output)
    procedure = report.next_tests[0].procedure
    assert 'Both cited histories retain warnings' not in procedure
    assert 'faulted histories retain warnings' in procedure
    assert "clean counterparts' recorded warning states" in procedure


def test_passing_trace_does_not_distract_from_unpaired_failing_patterns():
    from app.assistant.trace_reasoning import explanation_anchor
    packet, _, _, _ = captured()
    packet['observations'][0]['failed_cases'] = 0
    packet['observations'][1]['failed_cases'] = 1
    assert explanation_anchor(packet) is None
