"""Bounded, aligned excerpts of recorded development scores and warning states.

No scoring or alert simulation is performed. Streak counters describe the recorded
score sequence using the scorer's valid-reading convention, including prior-window
context. Samples never replace full traces for threshold sensitivity.
"""
import math

MAX_TRACE_POINTS = 8


def compatible_histories(clean, faulted):
    axes = [(point.cycle, point.rul) for point in faulted.points]
    compatible = (clean.fault is None and clean.scenario_id == 'clean' and faulted.fault is not None
        and clean.partition == faulted.partition and faulted.partition == 'out_of_fold'
        and clean.candidate == faulted.candidate and clean.config_id == faulted.config_id
        and clean.equipment_id == faulted.equipment_id and clean.failure_cycle == faulted.failure_cycle
        and clean.outcome.equipment_id == clean.equipment_id and faulted.outcome.equipment_id == faulted.equipment_id
        and clean.threshold == faulted.threshold and math.isfinite(faulted.threshold)
        and axes and axes == [(point.cycle, point.rul) for point in clean.points]
        and len({cycle for cycle, _ in axes}) == len(axes) and axes == sorted(axes)
        and all(cycle + rul == faulted.failure_cycle for cycle, rul in axes))
    return bool(compatible)


def matched_trace(clean, faulted, limits):
    if not compatible_histories(clean, faulted):
        return {'status': 'unavailable', 'reason': 'Missing or incompatible recorded development traces.'}
    axes = [(point.cycle, point.rul) for point in faulted.points]

    high = [0, 0]
    rows = []
    for left, right in zip(clean.points, faulted.points, strict=True):
        row = {'rul': right.rul}
        for index, (name, point) in enumerate((('clean', left), ('faulted', right))):
            finite = math.isfinite(point.score)
            above = point.score >= faulted.threshold if finite else None
            if finite:
                high[index] = high[index] + 1 if above else 0
            row.update({f'{name}_score': point.score if finite else None,
                f'{name}_warning_active': point.alert, f'{name}_high_streak': high[index]})
        rows.append(row)

    useful = [index for index, point in enumerate(faulted.points) if limits.min_useful_lead <= point.rul <= limits.horizon_cycles]
    # Anchor the useful window and first late point, then crossing/activation edges
    # with their preceding observation. Keep actual RULs; gaps are never interpolated.
    chosen = []
    def choose(index):
        if index not in chosen and 0 <= index < len(rows) and len(chosen) < MAX_TRACE_POINTS:
            chosen.append(index)
    if useful:
        choose(useful[0] - 1)
        choose(useful[0])
        choose(useful[-1])
        choose(useful[-1] + 1)
    candidates = useful or list(range(len(rows)))
    for index in candidates:
        if index == 0:
            continue
        previous, current = rows[index-1], rows[index]
        edge = any(previous[f'{name}_warning_active'] != current[f'{name}_warning_active'] or
            ((previous[f'{name}_score'] is not None and previous[f'{name}_score'] >= faulted.threshold) !=
             (current[f'{name}_score'] is not None and current[f'{name}_score'] >= faulted.threshold)) for name in ('clean', 'faulted'))
        if edge:
            choose(index-1)
            choose(index)
    for index in candidates:
        choose(index)
    for index in range(len(rows)):
        choose(index)
    rul_set = {faulted.points[index].rul for index in useful}
    return {'status': 'available', 'scope': 'selected_stored_history_excerpt_not_population',
        'total_recorded_points': len(rows), 'sampled_points': len(chosen), 'omitted_points': len(rows)-len(chosen),
        'useful_window_complete': rul_set == set(range(limits.min_useful_lead, limits.horizon_cycles+1)),
        'cycle_gaps_present': any(right[0] != left[0]+1 for left, right in zip(axes, axes[1:])),
        'useful_maximum_high_streak': {name: max((rows[index][f'{name}_high_streak'] for index in useful), default=0) for name in ('clean', 'faulted')},
        'persistence_convention': 'Valid scores in recorded order; invalid scores hold pending streaks and warning state. High streak includes earlier recorded points, not just the useful window. Cycle gaps do not reset the scorer.',
        'points': [rows[index] for index in sorted(chosen)]}


def trace_text(trace):
    if trace['status'] != 'available':
        return 'Matched score and warning trace unavailable.'
    points = []
    for point in trace['points']:
        def score(name):
            value = point[f'{name}_score']
            return f'{value:.6g}' if value is not None else 'unavailable'
        points.append(f"{point['rul']} cycles before failure: scores {score('clean')} → {score('faulted')}; "
            f"warning {'on' if point['clean_warning_active'] else 'off'} → {'on' if point['faulted_warning_active'] else 'off'}")
    return 'Scores cross thresholds; warnings turn on or off. Clean → faulted excerpt: ' + '; '.join(points) + '. ' + (
        f"{trace['omitted_points']} recorded points omitted; open the stored replay for the full trace. " if trace['omitted_points'] else '') + (
        'Some useful-window cycles are absent from the stored trace. ' if not trace['useful_window_complete'] else '')
