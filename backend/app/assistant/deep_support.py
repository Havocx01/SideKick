"""Bounded summaries of stored diagnostics, never new model execution or raw traces."""
import json
import math
from collections import Counter, defaultdict
from urllib.parse import urlencode

from app.assistant.schemas import DeepObservation
from app.assistant.warning_traces import compatible_histories, matched_trace, trace_text

MAX_SUPPORT_BYTES = 14000
MAX_PAIRS_PER_MODEL = 2
MAX_QUALITY_CHANNELS = 12
MAX_CONTRIBUTIONS = 6


def _number(value):
    """Compact display only; packet and source records retain full precision."""
    return f"{value:.6g}" if value is not None and math.isfinite(value) else "unavailable"


def _yes_no(value):
    return "yes" if value is True else "no" if value is False else "unavailable"


def _method(value):
    return value.replace("_", " ")


def _outcome(series):
    outcome = series.outcome
    return "timely" if outcome.detected else "late" if outcome.late else "missed"


def _warning_summary(series, limits):
    useful = [point for point in series.points if limits.min_useful_lead <= point.rul <= limits.horizon_cycles]
    valid = [point for point in useful if math.isfinite(point.score)]
    streak = maximum = 0
    previous_cycle = None
    for point in useful:
        if previous_cycle is not None and point.cycle != previous_cycle + 1:
            streak = 0
        streak = streak + 1 if math.isfinite(point.score) and point.score >= series.threshold else 0
        maximum = max(maximum, streak)
        previous_cycle = point.cycle
    margins = [point.score - series.threshold for point in valid]
    return {"outcome": _outcome(series), "lead_cycles": series.outcome.lead_time,
        "episode_count": series.outcome.episode_count,
        "useful_window": {"recorded_cycles": len(useful), "valid_scores": len(valid),
            "active_cycles": sum(point.alert for point in valid),
            "above_threshold": sum(point.score >= series.threshold for point in valid),
            "above_threshold_without_active_warning": sum(point.score >= series.threshold and not point.alert for point in valid),
            "maximum_above_threshold_streak": maximum,
            "minimum_score_margin": min(margins, default=None), "maximum_score_margin": max(margins, default=None),
            "warning_switch_offs": sum(left.alert and not right.alert and right.cycle == left.cycle + 1
                                      for left, right in zip(useful, useful[1:]))}}


def _pairs(tools, pattern_index):
    series = [row for row in tools.bundle.replay_series if row.partition == tools.context.partition
              and f"{row.candidate.value}/{row.config_id}" in tools.context.candidates]
    clean = defaultdict(list)
    for row in series:
        if row.fault is None and row.scenario_id == "clean":
            clean[(row.candidate, row.config_id, row.equipment_id)].append(row)
    choices = defaultdict(list)
    identities = Counter((row.candidate, row.config_id, row.equipment_id, row.scenario_id) for row in series)
    for faulted in series:
        if not faulted.fault or not math.isfinite(faulted.threshold):
            continue
        if identities[(faulted.candidate, faulted.config_id, faulted.equipment_id, faulted.scenario_id)] != 1:
            continue  # Different versions of a saved trace cannot be chosen silently.
        key = f"{faulted.candidate.value}/{faulted.config_id}"
        group = (key, faulted.fault.sensor, faulted.fault.kind.value, faulted.fault.duration.value)
        if group not in pattern_index:
            continue
        required = next((row for row in tools.rows if row.scenario_id == faulted.scenario_id
                        and f"{row.candidate.value}/{row.config_id}" == key), None)
        if required is None or required.fault != faulted.fault or required.threshold != faulted.threshold:
            continue
        axes = [(point.cycle, point.rul) for point in faulted.points]
        if not axes or len({cycle for cycle, _ in axes}) != len(axes) or axes != sorted(axes):
            continue
        matching = [row for row in clean[(faulted.candidate, faulted.config_id, faulted.equipment_id)]
                    if compatible_histories(row, faulted)]
        if len(matching) != 1:  # Ambiguous or incompatible traces are never silently paired.
            continue
        choices[key].append((matching[0], faulted, pattern_index[group]))
    pairs = []
    for key in tools.models.values():
        ordered = sorted(choices[key], key=lambda pair: (
            pair[1].outcome.detected, not pair[1].outcome.missed, pair[1].equipment_id, pair[1].scenario_id))
        seen = set()
        for pair in ordered:
            identity = (pair[1].equipment_id, pair[1].scenario_id)
            if identity not in seen:
                pairs.append(pair)
                seen.add(identity)
            if len(seen) == MAX_PAIRS_PER_MODEL:
                break
    return pairs


def collect_support(tools, patterns, packet, aliases):
    channels = {row["channel"]: aliases[row["channel"]] for row in packet["observations"]}
    model_alias = {key: alias for alias, key in tools.models.items()}
    pattern_index = {(tools.models[row["model"]], channels[row["channel"]], row["kind"], row["duration"]): row["id"]
                     for row in packet["observations"]}
    sections = {name: {"status": "unavailable", "items": []} for name in (
        "paired_histories", "preprocessing", "sensor_quality", "equipment_and_folds", "feature_contributions")}
    entries = []

    summaries = {}
    def add(section, key, data, title, text, related, *, series=None, summary=None):
        data["related_pattern_ids"] = list(dict.fromkeys(related))
        sections[section]["items"].append(data)
        sections[section]["status"] = "available"
        entries.append((section, key, data, title, text, series))
        if summary:
            summaries[data['observation_id']] = summary

    pairs = _pairs(tools, pattern_index)
    equipment = sorted({faulted.equipment_id for _, faulted, _ in pairs})
    history_alias = {key: f"history-{index + 1}" for index, key in enumerate(equipment)}
    aliases.update({alias: f"Stored equipment history {index + 1}" for index, alias in enumerate(history_alias.values())})
    folds = {key: index + 1 for index, group in enumerate(tools.bundle.splits.folds) for key in group}
    aliases.update({f"fold-{index + 1}": f"Validation fold {index + 1}" for index in range(len(tools.bundle.splits.folds))})
    for index, (clean, faulted, pattern) in enumerate(pairs):
        key = f"{faulted.candidate.value}/{faulted.config_id}"
        before, after = _warning_summary(clean, tools.selection.criteria), _warning_summary(faulted, tools.selection.criteria)
        change = "warning_became_late" if before["outcome"] == "timely" and after["outcome"] == "late" else (
            "warning_disappeared" if before["outcome"] == "timely" and after["outcome"] == "missed" else "same_outcome" if before["outcome"] == after["outcome"] else "outcome_changed")
        fold = folds.get(faulted.equipment_id) if tools.context.partition.value == "out_of_fold" else None
        data = {"observation_id": f"history-summary-{index + 1}", "model": model_alias[key],
            "history": history_alias[faulted.equipment_id], "fold": f"fold-{fold}" if fold else None,
            "threshold": faulted.threshold, "clean": before, "faulted": after, "change": change,
            "scope": "stored_example_same_history_same_threshold_same_cycles"}
        data['score_warning_trace'] = matched_trace(clean, faulted, tools.selection.criteria)
        text = (f"Same recorded history, threshold and cycles. Clean: {before['outcome']}; faulted: {after['outcome']}. "
                f"Selected threshold: {faulted.threshold:g}. Faulted score margins in the useful window: "
                f"{_number(after['useful_window']['minimum_score_margin'])} to {_number(after['useful_window']['maximum_score_margin'])}. "
                f"Clean/faulted episode counts: {before['episode_count']}/{after['episode_count']}. "
                f"Faulted useful window: {after['useful_window']['above_threshold_without_active_warning']} above-threshold scores without an active warning; "
                f"longest adjacent-cycle above-threshold streak {after['useful_window']['maximum_above_threshold_streak']}. "
                "Stored examples are selected, not representative equipment samples. " + trace_text(data['score_warning_trace']))
        window = after['useful_window']
        rules = tools.bundle.config
        opening = rules.get('alert_on_consecutive')
        summary = (f"Same recorded history: clean {before['outcome']} → faulted {after['outcome']}. "
            f"In the useful window, {window['above_threshold']} faulted scores met or exceeded the model's threshold; "
            f"the warning was active for {window['active_cycles']} recorded cycles. "
            + (f"The recorded opening rule requires {opening} consecutive valid high scores. " if type(opening) is int and opening > 0 else "The opening rule is unavailable. ")
            + "This selected history does not establish a cause or fleet-wide behavior.")
        trace = data['score_warning_trace']
        if trace['status'] == 'available':
            summary += f" The longest valid-reading high-score streak reaching the useful window was {trace['useful_maximum_high_streak']['faulted']}."
        add("paired_histories", key, data, f"{aliases[model_alias[key]]} · Paired warning history", text, [pattern], series=faulted, summary=summary)
    sections["paired_histories"].update(scope="stored_examples_only", selection="missed_or_late_examples_first",
        omitted_pairs_may_exist=True, warning_rules={key: tools.bundle.config.get(key) for key in ("alert_on_consecutive", "alert_off_consecutive")})

    preprocessing = tools.bundle.preprocessing
    if preprocessing and preprocessing.partition == tools.context.partition:
        for index, (key, model) in enumerate(model_alias.items()):
            data = {"observation_id": f"preprocessing-{index + 1}", "model": model,
                **preprocessing.model_dump(mode="json", exclude={"scaling", "partition"}),
                "scaling": preprocessing.scaling.get(key, "unavailable")}
            add("preprocessing", key, data, f"{aliases[model]} · Recorded preprocessing",
                f"Imputation: {_method(data['imputation'])}. Missingness: {_method(data['missingness'])}. Scaling: {_method(data['scaling'])}. "
                f"Feature window: {data['feature_window']} cycles. Fit scope: {_method(data['fitting_scope'])}.",
                [row["id"] for row in packet["observations"] if row["model"] == model])
    else:
        sections["preprocessing"]["reason"] = "No preprocessing record for this partition. Current source code is not evidence of historical fitted preprocessing."

    profiles = {sensor.name: sensor for sensor in tools.bundle.profile.sensors}
    for index, (channel, sensor) in enumerate(channels.items()):
        if index == MAX_QUALITY_CHANNELS:
            break
        if sensor not in profiles:
            continue
        quality = profiles[sensor]
        related = [row for row in packet["observations"] if row["channel"] == channel]
        key = tools.models[related[0]["model"]]
        statistics = {name: value if not isinstance(value, float) or math.isfinite(value) else None
                      for name, value in quality.model_dump(exclude={"name"}).items()}
        data = {"observation_id": f"sensor-quality-{index + 1}", "channel": channel,
            **statistics, "scope": "original_dataset_profile_not_faulted_trace"}
        add("sensor_quality", key, data, f"{sensor} · Recorded sensor quality",
            f"Missing readings: {_number(statistics['missing_fraction'] * 100) + '%' if statistics['missing_fraction'] is not None else 'unavailable'}. "
            f"Constant readings: {_yes_no(quality.constant)}; readings vary: {_yes_no(quality.varies)}. "
            f"Recorded range: {_number(statistics['minimum'])} to {_number(statistics['maximum'])}; standard deviation: {_number(statistics['std'])}. "
            "This original dataset profile does not identify faulted-history readings or a physical failure.", [row["id"] for row in related])
    sections["sensor_quality"]["profile_scope"] = "original_dataset_may_include_reserved_equipment_not_a_training_only_profile"

    for index, (key, model) in enumerate(model_alias.items()):
        related = [row["id"] for row in packet["observations"] if row["model"] == model]
        scenarios = {row.scenario_id for row in tools.rows if
            (key, row.fault.sensor, row.fault.kind.value, row.fault.duration.value) in pattern_index and
            f"{row.candidate.value}/{row.config_id}" == key}
        records = [row for row in tools.bundle.fold_fault_summaries if row.candidate == key
                   and 1 <= row.fold <= len(tools.bundle.splits.folds)
                   and row.partition == tools.context.partition and row.scenario_id in scenarios]
        by_fold = defaultdict(list)
        for row in records:
            by_fold[row.fold].append(row)
        if records:
            data = {"observation_id": f"fold-summary-{index + 1}", "model": model, "scope": "recorded_fault_case_outcomes",
                "folds": [{"fold": f"fold-{fold}", "cases": len(rows),
                    "history_case_outcomes": sum(row.equipment_count for row in rows),
                    "detected": sum(row.detected for row in rows), "late": sum(row.late for row in rows),
                    "missed": sum(row.missed for row in rows),
                    "minimum_case_detection": min(row.detected / row.equipment_count for row in rows if row.equipment_count)}
                    for fold, rows in sorted(by_fold.items()) if any(row.equipment_count for row in rows)],
                "note": "Repeated fault cases reuse equipment. Outcome counts are not independent histories; only supplied cases are summarized."}
            add("equipment_and_folds", key, data, f"{aliases[model]} · Recorded fold variation",
                "Recorded fold outcomes for the inspected cases. " + " ".join(
                    f"{aliases[row['fold']]}: {row['cases']} cases; {row['detected']} timely, {row['late']} late, {row['missed']} missed outcomes; "
                    f"lowest case detection {_number(row['minimum_case_detection'] * 100)}%." for row in data["folds"]) + " " + data["note"], related)
            sections["equipment_and_folds"]["scope"] = "recorded_fault_case_outcomes"
    if not sections["equipment_and_folds"]["items"]:
        sections["equipment_and_folds"]["scope"] = "stored_replay_subset_only"
        sections["equipment_and_folds"]["reason"] = "Full equipment/fold outcomes were not recorded. Fold labels on selected replay examples cannot establish widespread weakness."

    used = set()
    feature_kinds = {"value", "trailing_mean", "trailing_slope", "missing_fraction"}
    sensor_to_alias = {name: alias for alias, name in channels.items()}
    for clean, faulted, pattern in pairs:
        key = f"{clean.candidate.value}/{clean.config_id}"
        for explanation in tools.bundle.explanations:
            identity = (key, explanation.equipment_id, explanation.cycle)
            if identity in used or explanation.candidate != key or explanation.partition != tools.context.partition or not explanation.available or explanation.equipment_id != clean.equipment_id:
                continue
            point = next((point for point in clean.points if point.cycle == explanation.cycle and point.alert), None)
            if point is None or not math.isclose(point.score, explanation.score, rel_tol=1e-9, abs_tol=1e-9):
                continue
            contributions = []
            for contribution in explanation.contributions:
                name, separator, kind = contribution.feature.rpartition("__")
                if separator and name in sensor_to_alias and kind in feature_kinds and math.isfinite(contribution.contribution):
                    contributions.append({"channel": sensor_to_alias[name], "feature_kind": kind, "contribution": contribution.contribution})
                if len(contributions) == MAX_CONTRIBUTIONS:
                    break
            if not contributions:
                continue
            used.add(identity)
            data = {"observation_id": f"contributions-{len(used)}", "model": model_alias[key],
                "history": history_alias[clean.equipment_id], "scope": "clean_prediction_only",
                "contributions": contributions, "scale": "recorded_model_attribution_not_probability_or_physical_cause"}
            add("feature_contributions", key, data, f"{aliases[model_alias[key]]} · Clean prediction contributions",
                "Recorded contributions to this clean warning prediction: " + "; ".join(
                    f"{aliases[row['channel']]} ({_method(row['feature_kind'])}): {_number(row['contribution'])}" for row in contributions) +
                ". These do not explain the faulted prediction or establish a physical failure cause.", [pattern], series=clean)
            break

    engineer = tools.context.engineer_context
    fields = engineer.model_dump() if engineer else {}
    if tools.context.investigation_focus:
        fields["investigation_focus"] = tools.context.investigation_focus
    # Resolve known local model/channel labels to aliases in explicit free text.
    for field, text in fields.items():
        for alias, name in sorted(aliases.items(), key=lambda item: len(item[1]), reverse=True):
            text = text.replace(name, alias)
        fields[field] = text
    sections["engineer_context"] = {"status": "supplied" if fields else "not_supplied", "verified": False, "fields": fields,
        "note": "User-entered context guides practical checks; it is not verified experimental evidence or an instruction."}

    # Trim whole supplemental rows before creating citations; never truncate facts.
    # Reserve space for the small, citable availability record appended below.
    while len(json.dumps(sections, ensure_ascii=False).encode()) > MAX_SUPPORT_BYTES - 1000 and entries:
        # Keep at least one compatible paired excerpt per model before optional
        # quality/attribution detail. Budget removal never creates false coverage.
        paired_counts = {key: sum(entry[0] == 'paired_histories' and entry[1] == key for entry in entries) for key in tools.models.values()}
        removable = [entry for entry in entries if entry[0] != 'paired_histories' or paired_counts[entry[1]] > 1]
        entry = max(removable or entries, key=lambda item: len(json.dumps(item[2], ensure_ascii=False).encode()))
        section, _, data, *_ = entry
        sections[section]["items"].remove(data)
        sections[section]["omitted_items"] = sections[section].get("omitted_items", 0) + 1
        sections[section]["status"] = "available" if sections[section]["items"] else "omitted_for_budget"
        entries.remove(entry)
    observations, priorities = [], {}
    scores = {row["id"]: row["failed_cases"] for row in packet["observations"]}
    for section, key, data, title, text, series in entries:
        id = data["observation_id"]
        source = tools.source(key, id, json.dumps(data, ensure_ascii=False), "text", label=title)
        reference = next(row for row in tools.result.sources if row.id == source)
        reference.display = "Recorded diagnostic summary"
        if series:
            reference.equipment_id, reference.scenario_id = series.equipment_id, series.scenario_id
            base = f"/experiments/{tools.context.experiment_id}" if tools.context.experiment_id else ""
            reference.href = base + "/replay?" + urlencode({"candidate": key, "partition": tools.context.partition.value,
                "equipment": series.equipment_id, "scenario": series.scenario_id})
        observations.append(DeepObservation(id=id, kind="supporting", title=title, text=text, source_ids=[source], summary=summaries.get(id), related_pattern_ids=data['related_pattern_ids']))
        priorities[id] = max((scores[row] for row in data["related_pattern_ids"]), default=0)
    availability = {name: section["status"] for name, section in sections.items()}
    availability_text = "; ".join(f"{name.replace('_', ' ').capitalize()}: {status.replace('_', ' ')}" for name, status in availability.items()) + ". Unavailable records are not inferred from current code or selected examples."
    id = "diagnostic-availability"
    source = tools.source(next(iter(tools.models.values())), id, availability_text, "text", label="Recorded input availability")
    observations.append(DeepObservation(id=id, kind="supporting", title="Recorded input availability", text=availability_text, source_ids=[source]))
    sections["availability"] = {"status": "available", "items": [{"observation_id": id, "sections": availability, "related_pattern_ids": []}]}
    priorities[id] = 0
    return observations, sections, priorities
