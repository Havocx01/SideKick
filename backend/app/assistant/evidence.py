"""Read-only, configuration-scoped analysis of recorded evidence."""

import hashlib
import json
from urllib.parse import quote, urlencode

from app.assistant.schemas import AnalysisAction, AnalysisFinding, AnalysisRequest, AnalysisResult, EvidenceReference
from app.experiments.decision import candidateLabel
from app.schemas import EvidenceBundle, Partition

LABELS = {
    "qualifies": "Meets test limits", "required_passed": "Required fault cases passed",
    "required_scenarios": "Required fault cases", "detection_fraction": "Warned in time",
    "min_detection_fraction": "Minimum warned in time", "early_alarm_burden": "Early alarm time",
    "max_early_alarm_burden": "Maximum early alarm time", "recorded_required_cases": "Recorded required cases",
    "coverage_complete": "Coverage complete", "clean_detection": "Healthy sensors: warned in time",
    "clean_early_alarm_burden": "Healthy sensors: early alarm time", "mean_detection_required": "Average fault detection",
    "worst_burden_required": "Worst fault early alarm time", "alert_active": "Warning active",
    "remaining_life": "Cycles before failure", "episode_start": "Warning episode opened",
    "episode_end": "Warning episode closed", "history_outcome": "History outcome",
    "min_useful_lead": "Minimum useful lead", "horizon_cycles": "Warning window",
    "contribution_count": "Recorded contributions", "feature_contribution": "Feature contribution",
    "fault_onset_rul": "Fault onset before failure", "replay_count": "Stored replays for this model",
}
PARTITIONS = {Partition.out_of_fold: "Development", Partition.holdout: "Final validation"}


def percent(value) -> str:
    return "unavailable" if value is None else f"{value * 100:.2f}".rstrip("0").rstrip(".") + "%"


def display(value, unit: str) -> str:
    if value is None:
        return "Unavailable"
    if unit == "fraction":
        return percent(value)
    if unit == "boolean":
        return "Yes" if value else "No"
    if unit == "cycles":
        return f"{value} {'cycle' if value == 1 else 'cycles'}"
    if unit == "model attribution":
        return f"{value:+.4f}"
    if unit == "category":
        return str(value).capitalize()
    return str(value)


def build_analysis(bundle: EvidenceBundle, context: AnalysisRequest) -> AnalysisResult:
    if context.experiment_id != bundle.experiment_id:
        raise ValueError("The experiment does not match this evidence.")
    selection = bundle.final_evaluation if context.partition == Partition.holdout else bundle.development_selection
    if selection is None or selection.partition != context.partition:
        raise ValueError("No recorded evaluation is available in this partition.")
    candidates = {f"{v.candidate.value}/{v.config_id}": v for v in selection.ranked}
    if any(key not in candidates for key in context.candidates):
        raise ValueError("Choose a recorded model configuration in this partition.")
    prefix = f"/experiments/{quote(bundle.experiment_id, safe='')}" if bundle.experiment_id else ""
    names = {key: candidateLabel(verdict) for key, verdict in candidates.items()}
    scenario_names = {"clean": "Healthy sensors"}
    for row in bundle.scenario_results:
        if row.fault is not None:
            scenario_names.setdefault(row.scenario_id, row.fault.label())
    sources, findings, actions = [], [], []
    limits = ["Recorded test results do not approve deployment.",
              "Simulated sensor faults do not establish physical equipment failure causes.",
              "Development comparisons do not establish performance on new equipment."]

    def href(candidate, scenario=None, equipment=None, cycle=None):
        query = {"candidate": candidate, "partition": context.partition.value}
        if scenario is not None:
            query["scenario"] = scenario
        if equipment is not None:
            query["equipment"] = equipment
        if cycle is not None:
            query["cycle"] = cycle
        if equipment is not None:
            return f"{prefix}/replay?{urlencode(query)}"
        return f"{prefix}/comparison?{urlencode(query)}" + ("#fault-results" if scenario not in (None, "clean") else "")

    def source(candidate, metric, value, unit, scenario=None, equipment=None, cycle=None, label=None):
        parts = [names[candidate], PARTITIONS[context.partition]]
        if scenario is not None:
            parts.append(scenario_names.get(scenario, "Recorded fault case"))
        if equipment is not None:
            parts.append(f"History {equipment}")
        if cycle is not None:
            parts.append(f"Cycle {cycle}")
        item = EvidenceReference(id=f"s{len(sources)}", label=label or LABELS.get(metric, metric.replace("_", " ")),
                                 candidate=candidate, partition=context.partition, scenario_id=scenario,
                                 equipment_id=equipment, cycle=cycle, metric=metric,
                                 value=str(value) if value is not None else "unavailable", unit=unit,
                                 display=display(value, unit), context=" · ".join(parts),
                                 href=href(candidate, scenario, equipment, cycle))
        sources.append(item)
        return item.id

    def finding(title, detail, ids, tone="neutral"):
        findings.append(AnalysisFinding(id=f"f{len(findings)}", title=title, detail=detail, source_ids=ids, tone=tone))

    def replay_for(key, scenario):
        return next((s for s in bundle.replay_series if f"{s.candidate.value}/{s.config_id}" == key
                     and s.partition == context.partition and s.scenario_id == scenario), None)

    criteria = selection.criteria
    qualification_ids = {}
    for key in context.candidates:
        verdict = candidates[key]
        ids = [source(key, "qualifies", verdict.qualifies, "boolean"),
               source(key, "required_passed", verdict.required_passed, "cases"),
               source(key, "required_scenarios", verdict.required_scenarios, "cases")]
        qualification_ids[key] = ids
        finding("Meets test limits" if verdict.qualifies else "Does not meet test limits",
                f"{names[key]}: {verdict.required_passed} of {verdict.required_scenarios} required fault cases passed.",
                ids, "success" if verdict.qualifies else "danger")
        rows = [r for r in bundle.scenario_results if f"{r.candidate.value}/{r.config_id}" == key
                and r.partition == context.partition and r.required and r.fault is not None]
        if context.scenario_id and context.task != "warning" and not any(r.scenario_id == context.scenario_id for r in rows):
            raise ValueError("That scenario is not a recorded required case for this model.")
        cases = [("Healthy sensors", "clean", verdict.clean)] + [(r.fault.label(), r.scenario_id, r.metrics) for r in rows]
        for label, scenario, metrics in cases:
            if metrics.detection_fraction < criteria.min_detection_fraction:
                ids = [source(key, "detection_fraction", metrics.detection_fraction, "fraction", scenario),
                       source(key, "min_detection_fraction", criteria.min_detection_fraction, "fraction", scenario)]
                finding("Too few timely warnings", f"{label}: {percent(metrics.detection_fraction)} warned in time; minimum {percent(criteria.min_detection_fraction)}.", ids, "danger")
            if metrics.early_alarm_burden is None or metrics.early_alarm_burden > criteria.max_early_alarm_burden:
                ids = [source(key, "early_alarm_burden", metrics.early_alarm_burden, "fraction", scenario),
                       source(key, "max_early_alarm_burden", criteria.max_early_alarm_burden, "fraction", scenario)]
                detail = "Early alarm time is unavailable." if metrics.early_alarm_burden is None else f"{percent(metrics.early_alarm_burden)} early alarm time; maximum {percent(criteria.max_early_alarm_burden)}."
                finding("Early alarm limit", f"{label}: {detail}", ids, "warning")
        if not rows or len(rows) != verdict.required_scenarios or verdict.coverage_complete is False or any(r.coverage_complete is False for r in rows):
            finding("Incomplete evidence", "Required cases or equipment coverage are incomplete. Inspect coverage before drawing a conclusion.",
                    [source(key, "recorded_required_cases", len(rows), "cases"), source(key, "coverage_complete", verdict.coverage_complete, "boolean")], "warning")
        if rows:
            lowest = min(rows, key=lambda r: r.metrics.detection_fraction)
            burdened = [r for r in rows if r.metrics.early_alarm_burden is not None]
            highest = max(burdened, key=lambda r: r.metrics.early_alarm_burden) if burdened else None
            if highest is not None and highest.scenario_id == lowest.scenario_id:
                finding("Weakest fault case", f"{lowest.fault.label()}: lowest detection at {percent(lowest.metrics.detection_fraction)} and highest early alarm time at {percent(lowest.metrics.early_alarm_burden)}.",
                        [source(key, "detection_fraction", lowest.metrics.detection_fraction, "fraction", lowest.scenario_id),
                         source(key, "early_alarm_burden", lowest.metrics.early_alarm_burden, "fraction", lowest.scenario_id)])
            else:
                finding("Lowest fault detection", f"{lowest.fault.label()}: {percent(lowest.metrics.detection_fraction)} warned in time.",
                        [source(key, "detection_fraction", lowest.metrics.detection_fraction, "fraction", lowest.scenario_id)])
                if highest is not None:
                    finding("Highest early alarm time", f"{highest.fault.label()}: {percent(highest.metrics.early_alarm_burden)} of eligible early cycles in alarm.",
                            [source(key, "early_alarm_burden", highest.metrics.early_alarm_burden, "fraction", highest.scenario_id)])
            target = next((r.scenario_id for r in sorted(rows, key=lambda r: r.metrics.detection_fraction)
                           if r.scenario_id in verdict.failing_scenarios), None) or verdict.worst_scenario_id
            replay = replay_for(key, target) if context.task != "warning" else None
            if replay is not None:
                actions.append(AnalysisAction(id=f"a{len(actions)}", label="Open stored replay",
                                              detail=f"Watch {names[key]} on {scenario_names.get(target, 'the weakest fault case')}.",
                                              href=href(key, target, replay.equipment_id)))
            actions.append(AnalysisAction(id=f"a{len(actions)}", label="Inspect fault results", detail=f"Review the recorded fault matrix for {names[key]}.",
                                          href=href(key) + "#fault-results"))

    if context.task == "compare":
        first, second = (candidates[k] for k in context.candidates)
        keys = context.candidates
        outcome = {True: "meets", False: "does not meet"}
        overview = f"{names[keys[0]]} {outcome[first.qualifies]} the test limits; {names[keys[1]]} {outcome[second.qualifies]} them."
        compared = []
        for metric, left, right in [("clean_detection", first.clean.detection_fraction, second.clean.detection_fraction),
                                    ("clean_early_alarm_burden", first.clean.early_alarm_burden, second.clean.early_alarm_burden),
                                    ("worst_burden_required", first.worst_burden_required, second.worst_burden_required)]:
            ids = [source(keys[0], metric, left, "fraction"), source(keys[1], metric, right, "fraction")]
            detail = "A recorded value is missing; no difference is reported." if left is None or right is None else f"Second minus first: {(right - left) * 100:+.2f} percentage points."
            if first.clean.engines != second.clean.engines:
                detail = "The evaluated history counts differ; inspect each model separately."
            compared.append((LABELS[metric], detail, ids))
        same_cases = [{r.scenario_id for r in bundle.scenario_results if f"{r.candidate.value}/{r.config_id}" == k and r.partition == context.partition and r.required and r.fault} for k in keys]
        if same_cases[0] != same_cases[1] or first.required_scenarios != second.required_scenarios:
            limits.append("Fault coverage differs; passed-case totals cannot be compared as an improvement.")
        elif same_cases[0] and first.coverage_complete is not False and second.coverage_complete is not False:
            ids = [source(keys[0], "mean_detection_required", first.mean_detection_required, "fraction"),
                   source(keys[1], "mean_detection_required", second.mean_detection_required, "fraction")]
            compared.append(("Average fault detection", f"Second minus first: {(second.mean_detection_required - first.mean_detection_required) * 100:+.2f} percentage points across the same recorded fault cases.", ids))
        matched = next((p for p in bundle.paired_comparisons if p.kind == "matched_augmentation" and {p.first, p.second} == set(keys)), None) if context.partition == Partition.out_of_fold else None
        kind = ("Matched augmentation comparison: same configuration and seed, with and without fault-augmented training."
                if matched else "Independently selected configurations: differences do not isolate augmented training.")
        findings.insert(0, AnalysisFinding(id="overview", title="Comparison overview", detail=f"{overview} {kind}",
                                           source_ids=qualification_ids[keys[0]][:1] + qualification_ids[keys[1]][:1],
                                           tone="success" if first.qualifies and second.qualifies else "warning"))
        for title, detail, ids in compared:
            finding(title, detail, ids)
        limits.append("A matched augmentation comparison is recorded, conditional on these configurations and thresholds." if matched else "This compares selected configurations and does not isolate the effect of augmented training.")
        limits.append("Differences are descriptive; they do not establish statistical superiority.")
        recommended = selection.recommended
        limits.append(f"The recorded recommendation is unchanged: {candidateLabel(recommended)}." if recommended
                      else "No model met the recorded criteria; this comparison does not change that outcome.")

    if context.task == "warning":
        key = context.candidates[0]
        series = next((s for s in bundle.replay_series if f"{s.candidate.value}/{s.config_id}" == key and s.partition == context.partition and s.scenario_id == context.scenario_id and s.equipment_id == context.equipment_id), None)
        primary = "Recorded warning"
        if series is None:
            primary = "Replay unavailable"
            stored = sum(1 for s in bundle.replay_series if f"{s.candidate.value}/{s.config_id}" == key and s.partition == context.partition)
            finding(primary, "No replay is stored for this model, scenario and history. The model's recorded test results are shown instead.",
                    [source(key, "replay_count", stored, "histories")], "warning")
            limits.append("Without a stored replay, alert timing for this history cannot be explained.")
        else:
            cycle = context.cycle if context.cycle is not None else (series.episodes[0].start_cycle if series.episodes else series.points[-1].cycle if series.points else None)
            point = next((p for p in series.points if p.cycle == cycle), None)
            episode = next((e for e in series.episodes if cycle is not None and e.start_cycle <= cycle <= e.end_cycle), None)
            if point is None:
                primary = "Cycle not recorded"
                finding(primary, "The selected cycle is not stored in this replay. Stored alert episodes and the history outcome are shown instead.",
                        [source(key, "replay_count", len(series.points), "cycles", series.scenario_id, series.equipment_id, label="Stored replay cycles")], "warning")
            else:
                ids = [source(key, "alert_active", point.alert, "boolean", series.scenario_id, series.equipment_id, cycle),
                       source(key, "remaining_life", point.rul, "cycles", series.scenario_id, series.equipment_id, cycle)]
                detail = f"The recorded alert is {'active' if point.alert else 'inactive'} at cycle {cycle}, {display(point.rul, 'cycles')} before failure."
                if episode:
                    ids += [source(key, "episode_start", episode.start_cycle, "cycles", series.scenario_id, series.equipment_id, cycle), source(key, "episode_end", episode.end_cycle, "cycles", series.scenario_id, series.equipment_id, cycle)]
                    detail += f" Its stored episode runs from cycle {episode.start_cycle} to {episode.end_cycle}."
                finding(primary, detail, ids, "warning" if point.alert else "neutral")
            outcome = "in time" if series.outcome.detected else "late" if series.outcome.late else "missed"
            finding("History outcome", f"The stored history outcome is {outcome}. Useful warnings fall between {criteria.min_useful_lead} and {criteria.horizon_cycles} cycles before failure.",
                    [source(key, "history_outcome", outcome, "category", series.scenario_id, series.equipment_id), source(key, "min_useful_lead", criteria.min_useful_lead, "cycles"), source(key, "horizon_cycles", criteria.horizon_cycles, "cycles")],
                    "success" if series.outcome.detected else "danger")
            # Attribution records have no scenario ID: only clean traces are unambiguous.
            explanation = next((e for e in bundle.explanations if e.candidate == key and e.partition == context.partition and e.equipment_id == series.equipment_id and e.cycle == cycle and e.available), None) if series.fault is None and point is not None else None
            if explanation:
                finding("Model contributions available", "Recorded feature contributions describe this clean model prediction, not a physical failure cause.", [source(key, "contribution_count", len(explanation.contributions), "features", series.scenario_id, series.equipment_id, cycle)])
                for contribution in sorted(explanation.contributions, key=lambda item: abs(item.contribution), reverse=True)[:3]:
                    finding("Recorded feature contribution", f"{contribution.feature}: {contribution.contribution:+.4f} in the model's attribution scale.",
                            [source(key, "feature_contribution", contribution.contribution, "model attribution", series.scenario_id, series.equipment_id, cycle, label=f"Contribution: {contribution.feature}")])
            else:
                limits.append("No unambiguous feature attribution is recorded for this model, scenario and cycle.")
            if series.fault_onset_rul is not None:
                finding("Recorded fault onset", f"The simulated fault began {display(series.fault_onset_rul, 'cycles')} before failure.", [source(key, "fault_onset_rul", series.fault_onset_rul, "cycles", series.scenario_id, series.equipment_id)])
            actions.insert(0, AnalysisAction(id="replay", label="Open warning replay", detail="Inspect this recorded history and cycle.", href=href(key, series.scenario_id, series.equipment_id, cycle if point is not None else None)))
        # Keep the replay event primary; model-level evidence remains available below it.
        findings.sort(key=lambda f: f.title != primary)
    if context.task == "brief":
        limits.append("Engineer review draft. Verify findings and agree a next check before saving a decision.")
    titles = {"investigate": "Result investigation", "compare": "Model comparison", "warning": "Warning explanation", "brief": "Review brief"}
    digest_payload = {"context": context.model_dump(mode="json"), "fingerprint": bundle.config_fingerprint,
                      "source_digest": bundle.source_digest, "findings": [f.model_dump() for f in findings],
                      "sources": [s.model_dump(mode="json") for s in sources]}
    digest = hashlib.sha256(json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    result = AnalysisResult(title=titles[context.task], summary=findings[0].detail, findings=findings, sources=sources,
                            actions=actions, limitations=limits, evidence_digest=digest)
    return with_brief(result, context)


def with_brief(result: AnalysisResult, context: AnalysisRequest) -> AnalysisResult:
    """Attach a deterministic, editable review draft to brief analyses."""
    if context.task != "brief":
        return result
    by_id = {s.id: s for s in result.sources}
    cited = []
    for finding in result.findings[:3]:
        cited += [by_id[i] for i in finding.source_ids if i in by_id and by_id[i] not in cited]
    models = list(dict.fromkeys(s.context.split(" · ")[0] for s in result.sources)) or context.candidates
    lines = ["Engineer review draft", "",
             f"Experiment: {context.experiment_id or 'Recorded benchmark'} · {PARTITIONS[context.partition]}",
             f"Model: {', '.join(models)}", ""]
    if result.interpretation:
        lines += ["AI interpretation (verify against the evidence)", result.interpretation, ""]
    lines += ["Findings"] + [f"- {f.title}: {f.detail}" for f in result.findings[:3]]
    lines += ["", "Evidence"] + [f"- {s.label}: {s.display} ({s.context})" for s in cited[:6]]
    lines += ["", "Proposed next checks"] + ([f"- {a.label}: {a.detail}" for a in result.actions[:2]] or ["- Agree a next check with the equipment engineer."])
    lines += ["", "Limitations"] + [f"- {item}" for item in result.limitations]
    return result.model_copy(update={"brief_draft": "\n".join(lines)})
