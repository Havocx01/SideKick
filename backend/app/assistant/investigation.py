import hashlib
import json
import math
from decimal import Decimal, ROUND_CEILING
from urllib.parse import urlencode

from app.assistant.evidence import build_analysis, display, percent, with_brief
from app.assistant.schemas import AnalysisAction, AnalysisClaim, AnalysisFinding, AnalysisRequest, EvidenceReference, InvestigationCall
from app.experiments.decision import candidateLabel


PROMPT_VERSION = "sidekick-investigation-v4"
FAULT_CHECKS = {
    "dropout": "Check missing-reading flags and median imputation, then inspect late and missed warnings before retesting.",
    "stuck": "Check whether flat readings are flagged and whether the model relies on this channel before retesting.",
    "drift": "Check channel scaling and sensitivity to gradual offsets before retesting.",
}


TOOL_LABELS = {
    "get_model_metrics": "Check model limits",
    "list_fault_cases": "Find relevant fault cases",
    "inspect_fault_case": "Inspect a fault case",
    "compare_models": "Compare recorded models",
    "get_warning_events": "Inspect stored warning events",
    "get_dataset_checks": "Check data readiness",
    "suggest_column_mapping": "Review column mapping",
}


def toolSpec(name, properties=None):
    properties = properties or {}
    return {"type": "function", "name": name, "description": TOOL_LABELS[name], "strict": True,
            "parameters": {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}}


class EvidenceTools:
    def __init__(self, bundle, context: AnalysisRequest, result=None):
        self.bundle = bundle
        self.context = context
        self.result = (result or build_analysis(bundle, context)).model_copy(deep=True)
        self.result.assessment = []
        self.result.investigation = []
        self.models = {f"model-{i + 1}": key for i, key in enumerate(context.candidates)}
        self.selection = bundle.final_evaluation if context.partition.value == "holdout" else bundle.development_selection
        self.verdicts = {f"{row.candidate.value}/{row.config_id}": row for row in self.selection.ranked}
        self.rows = [row for row in bundle.scenario_results if row.partition == context.partition and row.required and row.fault
                     and f"{row.candidate.value}/{row.config_id}" in context.candidates]
        self.cases = {f"case-{i + 1}": case for i, case in enumerate(dict.fromkeys(row.scenario_id for row in self.rows))}
        self.claims = {}
        self.seenFindings = set()
        self.seenActions = set()
        self.listedCases = set()
        self.calls = []

    def fresh(self):
        return EvidenceTools(self.bundle, self.context)

    @property
    def specs(self):
        model = {"type": "string", "enum": list(self.models)}
        specs = [toolSpec("get_model_metrics", {"model": model}),
                 toolSpec("list_fault_cases", {"model": model, "order": {"type": "string", "enum": ["failed", "weakest_detection", "highest_early_alarm"]},
                                                "limit": {"type": "integer", "enum": [1, 2, 3]}}),
                 toolSpec("inspect_fault_case", {"model": model, "case": {"type": "string"}})]
        if self.context.task == "compare" or (self.context.task == "brief" and len(self.context.candidates) == 2):
            specs.append(toolSpec("compare_models"))
        if self.context.task == "warning" or (self.context.task == "brief" and self.context.equipment_id):
            specs.append(toolSpec("get_warning_events"))
        return specs

    def intro(self):
        return {"task": self.context.task, "models": list(self.models), "partition": self.context.partition.value,
                "warning_context_selected": self.context.task == "warning" or bool(self.context.equipment_id),
                "selected_case": next((alias for alias, id in self.cases.items() if id == self.context.scenario_id), None)}

    def source(self, key, metric, value, unit, scenario=None, label=None):
        sourceId = "i" + hashlib.sha256(f"{key}/{scenario}/{metric}".encode()).hexdigest()[:12]
        existing = next((source for source in self.result.sources if source.id == sourceId), None)
        if existing:
            return sourceId
        verdict = self.verdicts[key]
        modelName = next(source.context.split(" · ")[0] for source in self.result.sources if source.candidate == key)
        context = f"{modelName} · {'Final validation' if self.context.partition.value == 'holdout' else 'Development'}"
        if scenario:
            row = next(row for row in self.rows if row.scenario_id == scenario and f"{row.candidate.value}/{row.config_id}" == key)
            context += f" · {row.fault.label()}"
        base = f"/experiments/{self.context.experiment_id}" if self.context.experiment_id else ""
        query = {"candidate": key, "partition": self.context.partition.value}
        if scenario:
            query["scenario"] = scenario
        href = f"{base}/comparison?{urlencode(query)}" + ("#fault-results" if scenario else "")
        self.result.sources.append(EvidenceReference(id=sourceId, candidate=f"{verdict.candidate.value}/{verdict.config_id}",
            partition=self.context.partition, scenario_id=scenario, metric=metric, value=str(value) if value is not None else "unavailable",
            unit=unit, label=label or metric.replace("_", " ").capitalize(), display=display(value, unit), context=context, href=href))
        return sourceId

    def claim(self, id, text, sources):
        self.claims[id] = AnalysisClaim(id=id, text=text, source_ids=sources)
        return id

    def claim_catalog(self):
        """Selection needs meaning and values, never private names or validation messages."""
        refs = {source.id: source for source in self.result.sources}
        return [{"id": claim.id, "kind": claim.id.split("-", 1)[0],
                 "evidence": [{"metric": refs[id].metric, "value": refs[id].value, "unit": refs[id].unit,
                               "model": next(alias for alias, key in self.models.items() if key == refs[id].candidate),
                               "case": next((alias for alias, key in self.cases.items() if key == refs[id].scenario_id), None)}
                              for id in claim.source_ids]} for claim in self.claims.values()]

    def expose(self, findings, claims=None, extra=None):
        self.seenFindings.update(finding.id for finding in findings)
        sourceIds = list(dict.fromkeys([source for finding in findings for source in finding.source_ids]
                        + [source for id in claims or [] for source in self.claims[id].source_ids]))
        references = []
        for source in self.result.sources:
            if source.id in sourceIds:
                model = next(alias for alias, key in self.models.items() if key == source.candidate)
                case = next((alias for alias, key in self.cases.items() if key == source.scenario_id), None)
                references.append({"id": source.id, "model": model, "case": case, "metric": source.metric, "value": source.value, "unit": source.unit})
        # Actions are server-authored and remain bound to this evidence context.
        self.seenActions.update(action.id for action in self.result.actions)
        return {"finding_ids": [finding.id for finding in findings], "claims": claims or [], "evidence": references,
                "actions": [{"id": action.id, "kind": "replay" if "/replay?" in action.href else "fault_results"} for action in self.result.actions],
                **(extra or {})}

    def call(self, name, args, *, server_inspection=False):
        spec = next((spec for spec in self.specs if spec["name"] == name), None)
        if spec is None or not isinstance(args, dict) or set(args) != set(spec["parameters"]["properties"]):
            raise ValueError("Unsupported evidence tool or arguments.")
        for key, rules in spec["parameters"]["properties"].items():
            value = args[key]
            if rules["type"] == "string" and not isinstance(value, str):
                raise ValueError("Invalid evidence tool argument.")
            if rules["type"] == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
                raise ValueError("Invalid evidence tool argument.")
            if "enum" in rules and value not in rules["enum"]:
                raise ValueError("Evidence tool argument is outside this analysis.")
        packet = getattr(self, name)(**args)
        sourceIds = [source["id"] for source in packet.get("evidence", [])]
        label = f"Server inspection · {TOOL_LABELS[name]}" if server_inspection else TOOL_LABELS[name]
        self.calls.append(InvestigationCall(name=name, label=label, source_ids=sourceIds))
        return packet

    def get_model_metrics(self, model):
        key = self.models[model]
        verdict = self.verdicts[key]
        findings = [finding for finding in self.result.findings if any(source.id in finding.source_ids and source.candidate == key
                    and source.metric in ("qualifies", "coverage_complete") for source in self.result.sources)]
        qualification = next(source for source in self.result.sources if source.candidate == key and source.metric == "qualifies")
        claimId = self.claim(f"limits-{model}",
            f"The model meets the recorded test limits: {verdict.required_passed} / {verdict.required_scenarios} required fault cases passed. "
            "The next check is a locked-model evaluation on fresh reserved histories, not deployment approval." if verdict.qualifies else
            f"The model does not meet the recorded test limits: {verdict.required_scenarios - verdict.required_passed} of {verdict.required_scenarios} required fault cases did not pass. "
            "Resolve failed limits or missing coverage before a fresh validation check.",
            [qualification.id] + [s.id for s in self.result.sources if s.candidate == key and s.metric in ("required_passed", "required_scenarios")])
        if not verdict.qualifies:
            healthy = []
            criteria = self.selection.criteria
            if verdict.clean.detection_fraction < criteria.min_detection_fraction:
                healthy.append(f"Healthy detection is {percent(verdict.clean.detection_fraction)} against a {percent(criteria.min_detection_fraction)} minimum.")
                self.claims[claimId].source_ids += [self.source(key, "clean_detection", verdict.clean.detection_fraction, "fraction"),
                    self.source(key, "min_detection_fraction", criteria.min_detection_fraction, "fraction")]
            if verdict.clean.early_alarm_burden is None or verdict.clean.early_alarm_burden > criteria.max_early_alarm_burden:
                healthy.append("Healthy early-alarm time is unavailable." if verdict.clean.early_alarm_burden is None else
                    f"Healthy early-alarm time is {percent(verdict.clean.early_alarm_burden)} against a {percent(criteria.max_early_alarm_burden)} maximum.")
                self.claims[claimId].source_ids += [self.source(key, "clean_early_alarm_burden", verdict.clean.early_alarm_burden, "fraction"),
                    self.source(key, "max_early_alarm_burden", criteria.max_early_alarm_burden, "fraction")]
            if healthy:
                self.claims[claimId].text += " " + " ".join(healthy)
        if self.context.partition.value == "holdout":
            self.claims[claimId].text = self.claims[claimId].text.replace(
                "The next check is a locked-model evaluation on fresh reserved histories, not deployment approval.",
                "This is recorded final validation. Next, agree a supervised equipment pilot and acceptance criteria; this is not deployment approval.")
            if not verdict.qualifies:
                self.claims[claimId].text += " These histories have already been scored; any new validation needs genuinely fresh histories."
        claims = [claimId]
        allRows = [row for row in self.rows if f"{row.candidate.value}/{row.config_id}" == key]
        if len(allRows) != verdict.required_scenarios or verdict.coverage_complete is False or any(
                row.coverage_complete is False or row.metrics.engines != (row.expected_engines if row.expected_engines is not None else verdict.clean.engines) for row in allRows):
            refs = [self.source(key, "coverage_complete", verdict.coverage_complete, "boolean"),
                    self.source(key, "recorded_required_cases", len(allRows), "cases")]
            claims.insert(0, self.claim(f"coverage-{model}", "Required case coverage is incomplete or unconfirmed. Review coverage before using the recorded qualification.", refs))
        criteria = self.selection.criteria
        if verdict.clean.detection_fraction < criteria.min_detection_fraction:
            refs = [self.source(key, "clean_detection", verdict.clean.detection_fraction, "fraction"),
                    self.source(key, "min_detection_fraction", criteria.min_detection_fraction, "fraction")]
            claims.append(self.claim(f"healthy-detection-{model}", "Healthy readings already fall below the timely-warning requirement.", refs))
        burden = verdict.clean.early_alarm_burden
        if burden is None or burden > criteria.max_early_alarm_burden:
            refs = [self.source(key, "clean_burden", burden, "fraction"),
                    self.source(key, "max_early_alarm_burden", criteria.max_early_alarm_burden, "fraction")]
            claims.append(self.claim(f"healthy-burden-{model}", "Healthy early-alarm time is unavailable." if burden is None
                else "Healthy readings already exceed the early-alarm limit.", refs))
        return self.expose(findings, claims, {"healthy": verdict.clean.model_dump(mode="json"), "required_passed": verdict.required_passed,
            "required_cases": verdict.required_scenarios, "coverage_complete": verdict.coverage_complete,
            "limits": self.selection.criteria.model_dump(mode="json")})

    def caseRows(self, model):
        key = self.models[model]
        selected = self.context.scenario_id if self.context.task in ("investigate", "brief") and not self.context.equipment_id else None
        return [row for row in self.rows if f"{row.candidate.value}/{row.config_id}" == key and (not selected or row.scenario_id == selected)]

    def passes(self, row):
        criteria = self.selection.criteria
        verdict = self.verdicts[f"{row.candidate.value}/{row.config_id}"]
        return (row.metrics.detection_fraction >= criteria.min_detection_fraction and row.metrics.early_alarm_burden is not None
                and row.metrics.early_alarm_burden <= criteria.max_early_alarm_burden and row.coverage_complete is not False
                and row.metrics.engines == (row.expected_engines if row.expected_engines is not None else verdict.clean.engines))

    def list_fault_cases(self, model, order, limit):
        rows = self.caseRows(model)
        if order == "failed":
            rows = [row for row in rows if not self.passes(row)]
        if order == "highest_early_alarm":
            rows.sort(key=lambda row: row.metrics.early_alarm_burden if row.metrics.early_alarm_burden is not None else float("inf"), reverse=True)
        else:
            rows.sort(key=lambda row: (row.metrics.detection_fraction, row.scenario_id))
        cases = []
        for row in rows[:limit]:
            alias = next(alias for alias, key in self.cases.items() if key == row.scenario_id)
            self.listedCases.add((model, alias))
            cases.append({"case": alias, "kind": row.fault.kind.value, "duration": row.fault.duration.value,
                          "detection": row.metrics.detection_fraction, "early_alarm_time": row.metrics.early_alarm_burden,
                          "meets_limits": self.passes(row)})
        return {"cases": cases, "total_matching": len(rows), "shown": len(cases), "order": order}

    def inspect_fault_case(self, model, case):
        if (model, case) not in self.listedCases:
            raise ValueError("Choose a case returned by this investigation.")
        key = self.models[model]
        row = next(row for row in self.caseRows(model) if row.scenario_id == self.cases[case])
        verdict = self.verdicts[key]
        criteria = self.selection.criteria
        metrics = row.metrics
        ids = [self.source(key, "detection_fraction", metrics.detection_fraction, "fraction", row.scenario_id, "Warned in time"),
               self.source(key, "min_detection_fraction", criteria.min_detection_fraction, "fraction", row.scenario_id, "Minimum warned in time"),
               self.source(key, "early_alarm_burden", metrics.early_alarm_burden, "fraction", row.scenario_id, "Early alarm time"),
               self.source(key, "max_early_alarm_burden", criteria.max_early_alarm_burden, "fraction", row.scenario_id, "Maximum early alarm time"),
               self.source(key, "detected", metrics.detected, "histories", row.scenario_id, "Histories warned in time"),
               self.source(key, "engines", metrics.engines, "histories", row.scenario_id, "Histories tested"),
               self.source(key, "expected_engines", row.expected_engines if row.expected_engines is not None else verdict.clean.engines, "histories", row.scenario_id, "Expected histories"),
               self.source(key, "coverage_complete", row.coverage_complete, "boolean", row.scenario_id, "Coverage complete")]
        claims = []
        if metrics.detection_fraction < criteria.min_detection_fraction:
            gap = ""
            if metrics.engines > 0 and math.isclose(metrics.detection_fraction, metrics.detected / metrics.engines, abs_tol=1e-8):
                target = int((Decimal(str(criteria.min_detection_fraction)) * metrics.engines).to_integral_value(rounding=ROUND_CEILING))
                gap = f" {target - metrics.detected} more histories would need timely warnings to reach that target."
            claims.append(self.claim(f"detection-{model}-{case}",
                f"{row.fault.label()}: {metrics.detected} / {metrics.engines} histories warned in time ({percent(metrics.detection_fraction)}), "
                f"below the {percent(criteria.min_detection_fraction)} requirement.{gap}", ids[:2] + ids[4:6]))
        if metrics.early_alarm_burden is None or metrics.early_alarm_burden > criteria.max_early_alarm_burden:
            text = f"{row.fault.label()}: early alarm time is unavailable, so this case cannot establish qualification." if metrics.early_alarm_burden is None else (
                f"{row.fault.label()}: {percent(metrics.early_alarm_burden)} early-alarm time exceeds the {percent(criteria.max_early_alarm_burden)} limit. "
                "This measures time in alarm during eligible early cycles, not the probability that a warning is false.")
            claims.append(self.claim(f"burden-{model}-{case}", text, ids[2:4]))
        if row.coverage_complete is False or metrics.engines != (row.expected_engines if row.expected_engines is not None else verdict.clean.engines):
            claims.append(self.claim(f"coverage-{model}-{case}", "Equipment coverage is incomplete or unconfirmed. Review coverage before interpreting this case.", ids[5:]))
        if row.coverage_complete is not False and metrics.engines == verdict.clean.engines and verdict.clean.detected > metrics.detected:
            cleanId = self.source(key, "clean_detected", verdict.clean.detected, "histories", label="Healthy histories warned in time")
            difference = verdict.clean.detected - metrics.detected
            claims.append(self.claim(f"loss-{model}-{case}", f"The recorded fault case has {difference} fewer timely {'warning' if difference == 1 else 'warnings'} than healthy readings "
                f"with {metrics.engines} evaluated histories in each result. This shows sensitivity to the simulated sensor fault, not its physical failure cause.", [cleanId, ids[4], ids[5]]))
        if self.passes(row):
            margin = (metrics.detection_fraction - criteria.min_detection_fraction) * 100
            claims.append(self.claim(f"passed-{model}-{case}",
                f"{row.fault.label()}: {percent(metrics.detection_fraction)} warned in time, {margin:.2f} percentage points above the requirement; "
                f"early-alarm time is {percent(metrics.early_alarm_burden)} against a {percent(criteria.max_early_alarm_burden)} limit. "
                "Evaluated history counts match; this case alone does not establish performance on fresh equipment.", ids[:7]))
        if row.coverage_complete is None:
            limitation = "Historical fault cases have no explicit coverage flag. Stored history counts are checked; no completeness flag is invented."
            if limitation not in self.result.limitations:
                self.result.limitations.append(limitation)
        findingId = f"inspected-{model}-{case}"
        finding = AnalysisFinding(id=findingId, title="Inspected fault case", detail=f"{row.fault.label()}: {metrics.detected} / {metrics.engines} histories warned in time; {percent(metrics.early_alarm_burden)} early alarm time.",
                                  source_ids=ids, tone="neutral" if self.passes(row) else "danger")
        if not any(item.id == findingId for item in self.result.findings):
            self.result.findings.append(finding)
        actionId = f"inspect-{model}-{case}"
        if not any(action.id == actionId for action in self.result.actions):
            href = next(source.href for source in self.result.sources if source.id == ids[0])
            self.result.actions.insert(0, AnalysisAction(id=actionId, label="Inspect this fault",
                detail=f"{row.fault.label()}. {FAULT_CHECKS[row.fault.kind.value]}", href=href))
        return self.expose([finding], claims, {"metrics": metrics.model_dump(mode="json"), "meets_limits": self.passes(row),
            "fault": {"kind": row.fault.kind.value, "duration": row.fault.duration.value, "onset_before_failure": row.fault.onset_before_failure}})

    def compare_models(self):
        titles = {"Comparison overview", "Healthy sensors: warned in time", "Healthy sensors: early alarm time", "Worst fault early alarm time", "Average fault detection"}
        findings = [finding for finding in self.result.findings if finding.title in titles]
        overview = next(finding for finding in findings if finding.id == "overview")
        first, second = [self.verdicts[key] for key in self.context.candidates]
        names = [candidateLabel(verdict) for verdict in (first, second)]
        if first.qualifies != second.qualifies:
            index = 0 if first.qualifies else 1
            text = f"Only {names[index]} meets every recorded test limit; {names[1 - index]} does not. Use the qualifying model as the candidate for a fresh validation check, subject to coverage review."
        elif first.qualifies:
            text = f"Both {names[0]} and {names[1]} meet the recorded limits. Compare fault detection and early-alarm time before selecting a model for fresh validation."
        else:
            text = f"Neither {names[0]} nor {names[1]} meets every recorded limit. Resolve failed tests or missing coverage before fresh validation."
        if self.context.partition.value == "holdout":
            text += " These are already-scored final validation histories; repeating their evaluation is not a fresh check."
        claims = [self.claim("comparison-limits", text, overview.source_ids)]
        rows = [[row for row in self.rows if f"{row.candidate.value}/{row.config_id}" == key] for key in self.context.candidates]
        comparable = (bool(rows[0]) and {row.scenario_id for row in rows[0]} == {row.scenario_id for row in rows[1]}
            and first.required_scenarios == second.required_scenarios
            and all(len(own) == verdict.required_scenarios and verdict.coverage_complete is not False
                    and all(row.coverage_complete is not False and row.metrics.engines == verdict.clean.engines
                            and row.metrics.engines == (row.expected_engines if row.expected_engines is not None else verdict.clean.engines) for row in own)
                    for own, verdict in zip(rows, (first, second)))
            and first.clean.engines == second.clean.engines)
        matched = self.context.partition.value == "out_of_fold" and any(
            pair.kind == "matched_augmentation" and {pair.first, pair.second} == set(self.context.candidates) for pair in self.bundle.paired_comparisons)
        scope = ("Matched configuration and seed compare augmented training within these recorded configurations and thresholds." if matched else
                 "Independently selected configurations do not isolate the benefit of augmented training.")
        scope += " Differences do not establish statistical superiority or deployment approval."
        if not comparable:
            refs = [self.source(key, "recorded_required_cases", len(own), "cases") for key, own in zip(self.context.candidates, rows)]
            claims.insert(0, self.claim("comparison-coverage", "Fault coverage or evaluated history counts differ or are incomplete. "
                "Do not treat passed-case totals or detection differences as an improvement; review each model's coverage separately.", refs))
        if comparable and first.worst_metrics and second.worst_metrics and first.worst_metrics.engines == second.worst_metrics.engines:
            difference = second.worst_metrics.detected - first.worst_metrics.detected
            refs = [self.source(key, "detected", verdict.worst_metrics.detected, "histories", verdict.worst_scenario_id, "Histories warned in time")
                    for key, verdict in zip(self.context.candidates, (first, second)) if verdict.worst_scenario_id]
            if len(refs) == 2:
                direction = "more" if difference >= 0 else "fewer"
                text = f"{names[1]} retains {abs(difference)} {direction} timely warnings than {names[0]} in its own weakest required case "
                text += f"({second.worst_metrics.detected} / {second.worst_metrics.engines} versus {first.worst_metrics.detected} / {first.worst_metrics.engines}). The faults can differ; this is a descriptive comparison."
                if difference == 0:
                    text = f"Both models retain {first.worst_metrics.detected} / {first.worst_metrics.engines} timely warnings in their own weakest required cases. The faults can differ; this is a descriptive comparison."
                claims.insert(0, self.claim("comparison-warning-counts", text, refs))
        burdens = [verdict.worst_burden_required for verdict in (first, second)]
        refs = [self.source(key, "worst_burden_required", burden, "fraction") for key, burden in zip(self.context.candidates, burdens)]
        alarm = (f"Worst fault early-alarm time is {percent(burdens[0])} for {names[0]} and {percent(burdens[1])} for {names[1]}; lower means less time in alarm during eligible early cycles. "
                 if comparable and all(burden is not None for burden in burdens) else
                 "A comparable early-alarm tradeoff is unavailable; do not assume the model with higher detection also raises fewer early alarms. ")
        scopeRef = self.source(self.context.candidates[0], "matched_augmentation", matched, "boolean", label="Matched augmentation comparison")
        claims.append(self.claim("comparison-tradeoff", alarm + scope, refs + overview.source_ids + [scopeRef]))
        return self.expose(findings, claims, {"matched_augmentation": matched, "comparable_coverage": comparable})

    def get_warning_events(self):
        metrics = {"alert_active", "remaining_life", "episode_start", "episode_end", "history_outcome", "fault_onset_rul", "replay_count"}
        findings = [finding for finding in self.result.findings if any(source.id in finding.source_ids and source.metric in metrics for source in self.result.sources)]
        source = next((source for source in self.result.sources if source.metric == "alert_active"), None)
        claims = []
        if source:
            active = source.value == "True"
            remaining = next(source for source in self.result.sources if source.metric == "remaining_life")
            criteria = self.selection.criteria
            rul = int(remaining.value)
            phase = ("before the useful warning window; an active warning here is not an in-time detection" if rul > criteria.horizon_cycles else
                     "within the useful warning window; an active warning here counts toward timely detection" if rul >= criteria.min_useful_lead else
                     "too late for the minimum useful lead, even if a warning is active")
            refs = [source.id, remaining.id] + [s.id for s in self.result.sources if s.metric in ("min_useful_lead", "horizon_cycles")]
            claims.append(self.claim("warning-state", f"At cycle {source.cycle}, the stored warning is {'active' if active else 'inactive'} with {rul} cycles before failure. "
                f"This is {phase}. The useful window is {criteria.min_useful_lead}–{criteria.horizon_cycles} cycles before failure; the score alone is not the warning state.", refs))
            clean = next((series for series in self.bundle.replay_series if series.partition == self.context.partition and series.fault is None
                and f"{series.candidate.value}/{series.config_id}" == self.context.candidates[0] and series.equipment_id == self.context.equipment_id), None)
            point = next((point for point in clean.points if point.cycle == source.cycle), None) if clean else None
            if point:
                query = {"candidate": self.context.candidates[0], "partition": self.context.partition.value,
                         "scenario": clean.scenario_id, "equipment": clean.equipment_id, "cycle": point.cycle}
                base = f"/experiments/{self.context.experiment_id}" if self.context.experiment_id else ""
                cleanRef = EvidenceReference(id="warning-clean-state", label="Healthy warning at this cycle", candidate=self.context.candidates[0],
                    partition=self.context.partition, scenario_id=clean.scenario_id, equipment_id=clean.equipment_id, cycle=point.cycle,
                    metric="healthy_alert_active", value=str(point.alert), unit="boolean", display=display(point.alert, "boolean"),
                    context=f"{source.context.split(' · ')[0]} · Healthy readings · Cycle {point.cycle}", href=f"{base}/replay?{urlencode(query)}")
                self.result.sources.append(cleanRef)
                text = "Healthy and selected readings have the same stored warning state at this cycle." if point.alert == active else "The selected scenario changes the stored warning state at this cycle compared with healthy readings. This does not establish a physical failure cause."
                claims.append(self.claim("warning-clean-comparison", text, [source.id, cleanRef.id]))
        else:
            refs = [source.id for source in self.result.sources if source.metric == "replay_count"]
            claims.append(self.claim("warning-unavailable", "The selected replay or cycle is unavailable. This history's warning state cannot be reconstructed from these results.", refs))
        outcome = next((source for source in self.result.sources if source.metric == "history_outcome"), None)
        if outcome:
            meaning = {"in time": "at least one stored warning occurred in the useful window", "late": "warnings did not provide the minimum useful lead",
                       "missed": "no warning was recorded in the useful or late-warning window"}
            claims.insert(1, self.claim("warning-outcome", f"History outcome: {outcome.value} — {meaning[outcome.value]}. "
                "This describes the full trace, so it can differ from the warning state at the selected cycle.", [outcome.id]))
        if not source and not any(action.id == "replay" for action in self.result.actions):
            self.result.actions = []
        return self.expose(findings, claims)

    def finish(self, findingIds, claimIds, actionId, model):
        if not findingIds or len(findingIds) > 3 or len(set(findingIds)) != len(findingIds) or any(id not in self.seenFindings for id in findingIds):
            raise ValueError("Choose findings from evidence actually inspected.")
        if not claimIds or len(claimIds) > 3 or len(set(claimIds)) != len(claimIds) or any(id not in self.claims for id in claimIds):
            raise ValueError("Choose verified claims from this investigation.")
        if actionId is not None and actionId not in self.seenActions:
            raise ValueError("Choose an available evidence action.")
        # Critical conclusions cannot be displaced by interesting but secondary metrics.
        # These are already inspected server claims; never broaden the evidence scope.
        task = self.context.task
        if task == "data":
            issues = [f for f in self.result.findings if f.tone in ("danger", "warning") and f.id != "data-validation"]
            important = next((f"data-issue-{f.id}" for f in issues if f"data-issue-{f.id}" in self.claims), None)
            required = ["data-readiness"] + ([important] if important else []) + ["mapping-review"]
        elif task == "warning" or (task == "brief" and self.context.equipment_id):
            required = ["warning-unavailable" if "warning-unavailable" in self.claims else "warning-state", "warning-outcome"]
        elif task == "compare" or (task == "brief" and len(self.context.candidates) == 2):
            required = ["comparison-coverage", "comparison-limits", "comparison-tradeoff", "comparison-warning-counts"]
        else:
            required = ["coverage-model-1", "limits-model-1"]
        claimIds = list(dict.fromkeys([id for id in required if id in self.claims] + claimIds))[:3]
        findings = {finding.id: finding for finding in self.result.findings}
        self.result.findings = [findings[id] for id in findingIds] + [finding for finding in self.result.findings if finding.id not in findingIds]
        self.result.assessment = [self.claims[id] for id in claimIds]
        sourceIds = {source.id for source in self.result.sources}
        if any(not claim.source_ids or not set(claim.source_ids) <= sourceIds for claim in self.result.assessment):
            raise ValueError("Assessment references are incomplete.")
        self.result.investigation = self.calls
        orderedIds = list(dict.fromkeys([id for claim in self.result.assessment for id in claim.source_ids]
                          + [id for finding in self.result.findings[:len(findingIds)] for id in finding.source_ids]))
        references = {source.id: source for source in self.result.sources}
        self.result.sources = [references[id] for id in orderedIds] + [source for source in self.result.sources if source.id not in orderedIds]
        # The provider can choose an inspected action, but cannot demote the
        # concrete fault check behind a generic navigation link. Prefer selected
        # cases, then other cases actually inspected inside this exact context.
        selectedSources = {id for claim in self.result.assessment for id in claim.source_ids}
        selectedSources.update(id for findingId in findingIds for id in findings[findingId].source_ids)
        relevantCases = {(source.candidate, source.scenario_id) for source in self.result.sources
                         if source.id in selectedSources and source.scenario_id is not None}
        specificActions = {f"inspect-{model}-{case}" for model, candidate in self.models.items()
                           for case, scenario in self.cases.items() if (candidate, scenario) in relevantCases}
        inspectedSources = {id for call in self.calls if call.name == "inspect_fault_case" for id in call.source_ids}
        inspectedCases = {(source.candidate, source.scenario_id) for source in self.result.sources if source.id in inspectedSources}
        inspectedActions = {f"inspect-{model}-{case}" for model, candidate in self.models.items()
                            for case, scenario in self.cases.items() if (candidate, scenario) in inspectedCases}
        self.result.actions.sort(key=lambda action: (
            0 if action.id in specificActions and action.id in inspectedActions else
            1 if action.id in inspectedActions and action.id in self.seenActions else 2,
            action.id != actionId))
        self.result.interpretation = None
        self.result.mode = "ai" if model else "evidence"
        self.result.model = model
        self.result.prompt_version = PROMPT_VERSION
        self.result.verification = "All assessments resolve to server-verified claims and scoped evidence. AI supplies no numbers, URLs or qualification decisions."
        payload = {"original": self.result.evidence_digest, "sources": [source.model_dump(mode="json") for source in self.result.sources],
                   "assessment": [claim.model_dump() for claim in self.result.assessment], "calls": [call.model_dump() for call in self.calls]}
        self.result.evidence_digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return with_brief(self.result, self.context)

    def local(self):
        findingIds, claimIds = [], []
        if self.context.task == "warning" or (self.context.task == "brief" and self.context.equipment_id):
            packet = self.call("get_warning_events", {})
            return self.finish(packet["finding_ids"][:3], packet["claims"][:3],
                "replay" if any(action.id == "replay" for action in self.result.actions) else None, None)
        if self.context.task == "compare" or (self.context.task == "brief" and len(self.context.candidates) == 2):
            packet = self.call("compare_models", {})
            return self.finish(packet["finding_ids"][:3], packet["claims"][:3], None, None)
        for model in self.models:
            packet = self.call("get_model_metrics", {"model": model})
            findingIds += packet["finding_ids"][:1]
            claimIds += packet["claims"]
            order = "failed" if not self.verdicts[self.models[model]].qualifies else "weakest_detection"
            cases = self.call("list_fault_cases", {"model": model, "order": order, "limit": 1})["cases"]
            if not cases and self.context.scenario_id and self.context.task != "warning":
                cases = self.call("list_fault_cases", {"model": model, "order": "weakest_detection", "limit": 1})["cases"]
            if cases:
                packet = self.call("inspect_fault_case", {"model": model, "case": cases[0]["case"]})
                findingIds = packet["finding_ids"][:1] + findingIds
                claimIds += packet["claims"]
        actionId = next((action.id for action in self.result.actions if action.id.startswith("inspect-")), None)
        result = self.finish(list(dict.fromkeys(findingIds))[:3], list(dict.fromkeys(claimIds))[:3], actionId, None)
        return result
