"""Qualitative anchors from selected recorded histories, never causal diagnoses.

Complete useful-window summaries and valid-reading streaks own these conditions.
Sparse displayed samples cannot establish them. Provider selections remain private
to admission; saved/public hypotheses keep their existing schema.
"""
import re
from typing import Literal

TraceBasis = Literal['no_useful_crossings', 'short_crossings', 'sustained_crossings_without_warning', 'warning_retained']

TITLES = {
    'no_useful_crossings': 'Possible reasons for absent useful-window score crossings',
    'short_crossings': 'Possible reasons for short score-crossing streaks',
    'sustained_crossings_without_warning': 'Possible timing or warning-state mismatch',
    'warning_retained': 'Possible score-response changes with retained warnings',
}


def trace_options(packet):
    """Only classify complete, all-valid useful windows; otherwise abstain."""
    section = packet['supporting_evidence']['paired_histories']
    opening = section.get('warning_rules', {}).get('alert_on_consecutive')
    options = {}
    for row in section['items']:
        trace = row.get('score_warning_trace', {})
        window = row['faulted']['useful_window']
        if (trace.get('status') != 'available' or trace.get('useful_window_complete') is not True
                or window['recorded_cycles'] <= 0 or window['valid_scores'] != window['recorded_cycles']):
            continue
        crossings = window['above_threshold']
        high = trace.get('useful_maximum_high_streak', {}).get('faulted')
        # Streak includes earlier recorded context, rather than starting at the window.
        if type(high) is not int or high < 0:
            continue
        if window['active_cycles'] > 0:
            if crossings > 0:
                options[row['observation_id']] = 'warning_retained'
        elif crossings == high == 0:
            options[row['observation_id']] = 'no_useful_crossings'
        elif crossings > 0 and type(opening) is int and opening > 0 and high > 0:
            options[row['observation_id']] = ('short_crossings' if high < opening
                else 'sustained_crossings_without_warning')
    return options


def explanation_anchor(packet):
    """One compatible history, failure-first. Never combine different conditions."""
    options = trace_options(packet)
    patterns = {row['id']: row for row in packet['observations']}
    failures_present = any(row['failed_cases'] for row in patterns.values())
    choices = [(patterns[id]['failed_cases'], row, id)
        for row in packet['supporting_evidence']['paired_histories']['items']
        if row['observation_id'] in options for id in row['related_pattern_ids']
        if id in patterns and (not failures_present or patterns[id]['failed_cases'] > 0)]
    if not choices:
        return None
    _, row, id = max(choices, key=lambda value: value[0])
    basis = options[row['observation_id']]
    return {'model': row['model'], 'observation_ids': [id, row['observation_id']], 'trace_basis': basis,
        'recommended_signal': 'scores_below_own_threshold' if basis == 'no_useful_crossings' else 'crossings_without_warning',
        'condition': {'short_crossings': 'This selected faulted history has crossings, but its longest valid high-score streak is shorter than the opening rule; persistence alone is not a proven defect.',
            'no_useful_crossings': 'This selected faulted history has no useful-window threshold crossings; persistence alone cannot activate a warning.',
            'sustained_crossings_without_warning': 'This selected history has sustained crossings but no active useful-window warning; inspect timing and prior state without declaring a logic defect.',
            'warning_retained': 'This selected faulted history has threshold crossings AND active warnings. Explore differences in crossing timing or warning lead; do not claim that all scores remained below threshold or warnings disappeared.'}[basis],
        'clean_outcome': row['clean']['outcome'], 'faulted_outcome': row['faulted']['outcome']}


def grounded_title(hypothesis, packet, patterns, records):
    """Return a tentative title only for an evidence-compatible, scoped explanation."""
    ids = set(hypothesis.observation_ids)
    cited_patterns = ids.intersection(patterns)
    if not cited_patterns:
        return None
    models = {patterns[id]['model'] for id in cited_patterns}
    for id in ids - cited_patterns:
        row = records.get(id)
        if (not row or (row.get('model') is not None and row['model'] not in models)
                or not cited_patterns.intersection(row.get('related_pattern_ids', []))):
            return None
    pairs = packet['supporting_evidence']['paired_histories']['items']
    relevant = [row for row in pairs if cited_patterns.intersection(row['related_pattern_ids'])]
    basis = hypothesis.trace_basis
    if not relevant:
        return 'Possible mechanism to investigate' if basis is None else None
    options = trace_options(packet)
    selected = [row for row in relevant if row['observation_id'] in ids]
    if not selected or basis is None or any(options.get(row['observation_id']) != basis for row in selected):
        return None
    # Supporting citations cannot import another pattern/model or expand one matched
    # history into a conclusion about all cited faults or all equipment.
    covered = {id for row in selected for id in row['related_pattern_ids']}
    if not cited_patterns <= covered:
        return None
    text = hypothesis.explanation
    explicit_history = any(re.search(rf'\b{re.escape(row["observation_id"])}\b', text, re.I) for row in selected)
    if not explicit_history and not re.search(r'\bselected\b|\bmatched\b|\bthis history\b|\bthese histories\b', text, re.I):
        return None
    if basis == 'no_useful_crossings':
        specific = re.search(r'\bbelow\b', text, re.I) and re.search(r'\bthreshold\b', text, re.I)
        # With no useful crossings, persistence alone is not a competing explanation.
        if re.search(r'\bpersistence\b|\b(?:sustained|brief\w*|isolated).*cross|\bcross\w*.*\b(?:brief\w*|isolated|sustained)\b', hypothesis.alternative, re.I):
            return None
    elif basis == 'short_crossings':
        specific = re.search(r'\bcross\w*\b', text, re.I) and re.search(r'\b(?:brief\w*|short|isolated|transient|intermittent|streaks?)\b', text, re.I)
    elif basis == 'warning_retained':
        specific = re.search(r'\bwarn\w*\b', text, re.I) and re.search(r'\b(?:active|timely|retained|sustained|timing|lead|cross\w*)\b', text, re.I)
        if re.search(r'\b(?:no|without|absent|missed|disappear\w*)\b[^.;]{0,40}\bwarnings?\b', text, re.I):
            return None
    else:
        specific = re.search(r'\bcross\w*\b', text, re.I) and re.search(r'\b(?:sustained|streaks?)\b', text, re.I)
    # Known crossings cannot be redescribed as uniformly absent, even tentatively.
    joined = text + ' ' + hypothesis.alternative
    if basis != 'no_useful_crossings' and re.search(r'\ball\b[^.;]{0,70}\bbelow\b|\bnever\s+cross\w*\b|\bno\s+(?:useful[- ]window\s+|score\s+)?crossings\b', joined, re.I):
        return None
    if re.search(r'\b(?:all|every)\s+(?:equipment|histories|faults|patterns)\b|\b(?:faulty|broken|defective)\s+(?:logic|persistence|rules?)\b', joined, re.I):
        return None
    if basis == 'sustained_crossings_without_warning' and re.search(r'\bthreshold\b.*\b(?:too high|stringen\w*|block\w*|prevent\w*)\b', joined, re.I):
        return None
    return TITLES[basis] if specific else None
