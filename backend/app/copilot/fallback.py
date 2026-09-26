"""Deterministic answers, used when no language model is available."""

from __future__ import annotations

from app.copilot.tools import ToolRegistry
from app.copilot.verify import annotate, unverified, verify_answer
from app.schemas import CopilotAnswer, ToolInvocation

_ROBUSTNESS = ("fault", "robust", "dropout", "stuck", "drift", "sensor fail", "survive", "degrade")
_RECOMMEND = ("recommend", "which model", "best", "choose", "pick", "select", "should i use", "winner")
_DATA = ("data", "quality", "profile", "column", "missing", "constant", "upload", "channel")
_METRIC = ("detection", "lead time", "burden", "false alarm", "alarm", "missed", "late", "interval")


def answer_without_llm(question: str, registry: ToolRegistry, *, reason: str) -> CopilotAnswer:
    lowered = question.lower()
    if any(word in lowered for word in _DATA) and not any(word in lowered for word in _RECOMMEND):
        text, calls, payloads = _data_answer(registry)
    elif any(word in lowered for word in _ROBUSTNESS):
        text, calls, payloads = _robustness_answer(registry)
    elif any(word in lowered for word in _METRIC):
        text, calls, payloads = _metric_answer(registry)
    else:
        text, calls, payloads = _recommendation_answer(registry)

    preface = (
        f"*Answered directly from the recorded evidence because {reason}. "
        "Figures below are read from stored metrics.*\n\n"
    )
    claims = verify_answer(text, payloads)
    return CopilotAnswer(
        text=preface + annotate(text, claims),
        tool_calls=calls,
        citations=sorted({runId for call in calls for runId in call.run_ids}),
        claims=claims,
        unverified_claims=len(unverified(claims)),
        degraded=True,
    )


def _invoke(registry: ToolRegistry, name: str, arguments: dict | None = None):
    payload = registry.call(name, arguments or {})
    # Keep source links for deterministic answers as well as model-written ones.
    runIds: set[str] = set()
    pending: list[object] = [payload]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            if isinstance(item.get("run_id"), str):
                runIds.add(item["run_id"])
            runIds.update(value for value in item.get("run_ids", []) if isinstance(value, str))
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return payload, ToolInvocation(name=name, arguments=arguments or {}, ok=True, run_ids=sorted(runIds))


def _percent(value: float | None) -> str:
    return "not measured" if value is None else f"{value:.0%}"


def _recommendation_answer(registry: ToolRegistry):
    report, call = _invoke(registry, "draft_report")
    lines: list[str] = []

    criteria = report["criteria"]
    lines.append(
        f"**Criteria set before selection:** detect at least "
        f"{_percent(criteria['min_detection_fraction'])} of failures between "
        f"{criteria['horizon_cycles']} and {criteria['min_useful_lead']} cycles before "
        f"failure, with no more than "
        f"{criteria['max_early_alarm_burden']:.1%} of healthy cycles spent in alarm."
    )

    if report["outcome"] == "none_qualified" or report["recommended"] is None:
        lines.append(
            "\n**No candidate qualified.** None met the criteria on clean data and on "
            "every case in the required fault set, so no model is recommended. That is "
            "a result about these candidates on this data, not a failure of the tool."
        )
    else:
        best = report["recommended"]
        ci = best["clean_detection_ci"]
        lines.append(
            f"\n**Recommended:** {best['candidate']} ({best['config_id']}), alerting at "
            f"a score of {best['threshold']:.4f}."
        )
        lines.append(
            f"- Clean out-of-fold detection {_percent(best['clean_detection_fraction'])} "
            f"(95% interval {ci['lower']:.2f} to {ci['upper']:.2f})"
        )
        lines.append(
            f"- Early alarm burden {best['clean_early_alarm_burden']:.1%}; median warning "
            f"lead time {best['median_lead_time']} cycles"
        )
        lines.append(
            f"- Worst required fault case {_percent(best['worst_required_detection'])}, on "
            f"{best['worst_required_scenario']}"
        )

    if report["uncertain_comparisons"]:
        lines.append(
            f"\n**Ordering not established:** {len(report['uncertain_comparisons'])} "
            "adjacent comparisons have overlapping detection intervals, so those "
            "rankings are not supported by this evaluation."
        )

    lines.append(
        f"\nEvaluated on {report['partitions']['development_engines']} development "
        f"engines across {report['partitions']['folds']} engine-grouped folds, with "
        f"{report['partitions']['holdout_engines']} engines held back."
    )
    if not report["final_evaluation_run"]:
        lines.append(
            "No final evaluation is attached to this protocol revision. These are "
            "development figures, not final validation."
        )
    return "\n".join(lines), [call], [report]


def _robustness_answer(registry: ToolRegistry):
    faults, faultCall = _invoke(registry, "run_fault_tests", {"required_only": True})
    report, reportCall = _invoke(registry, "draft_report")

    if not faults.get("per_candidate"):
        return ("No fault scenarios are recorded in this evidence bundle.", [faultCall], [faults])

    lines = [
        f"**Fault tests:** {faults['scenarios']} required cases covering "
        f"{', '.join(faults['fault_kinds'])} across "
        f"{len(faults['sensors_tested'])} sensors.",
        "",
        "| Candidate | Clean | Mean under fault | Worst case |",
        "| --- | --- | --- | --- |",
    ]
    ordered = sorted(faults["per_candidate"].items(), key=lambda item: -item[1]["mean_detection_fraction"])
    for name, entry in ordered:
        lines.append(
            f"| {name} | {_percent(entry['clean_detection_fraction'])} | "
            f"{_percent(entry['mean_detection_fraction'])} | "
            f"{_percent(entry['worst_detection_fraction'])} ({entry['worst_case']}) |"
        )

    worstHit = min(ordered, key=lambda item: item[1]["worst_detection_fraction"])
    bestHit = max(ordered, key=lambda item: item[1]["worst_detection_fraction"])
    lines.append("")
    lines.append(
        f"The largest exposure is {worstHit[0]}, which falls to "
        f"{_percent(worstHit[1]['worst_detection_fraction'])} on "
        f"{worstHit[1]['worst_case']}. The most stable is {bestHit[0]}, holding "
        f"{_percent(bestHit[1]['worst_detection_fraction'])} in its worst case."
    )
    lines.append(
        "\nThe age baseline reads no sensor, so it is unaffected by every one of these "
        "cases by construction. A sensor model that falls below it under fault is not "
        "worth deploying for that fault."
    )
    return "\n".join(lines), [faultCall, reportCall], [faults, report]


def _metric_answer(registry: ToolRegistry):
    rows, call = _invoke(registry, "query_runs", {"scenario_id": "clean", "limit": 20})
    if not rows.get("results"):
        return "No clean results are recorded in this bundle.", [call], [rows]

    lines = [
        "**Clean out-of-fold results.** Detection counts equipment, not cycles.",
        "",
        "| Candidate | Detected | Late | Missed | Detection | 95% interval | Burden | Median lead |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in sorted(rows["results"], key=lambda r: -r["metrics"]["detection_fraction"]):
        metrics = row["metrics"]
        lead = metrics["median_lead_time"]
        lines.append(
            f"| {row['candidate']} | {metrics['detected']}/{metrics['engines']} | "
            f"{metrics['late']} | {metrics['missed']} | "
            f"{_percent(metrics['detection_fraction'])} | "
            f"{metrics['detection_ci_lower']:.2f}-{metrics['detection_ci_upper']:.2f} | "
            f"{metrics['early_alarm_burden']:.1%} | "
            f"{'-' if lead is None else f'{lead:.1f}'} |"
        )
    lines.append(
        "\nA late warning arrived inside the final cycles, too late to act on. A miss "
        "produced neither a useful nor a late warning; early-only alarms may still "
        "have occurred. They are counted separately on purpose."
    )
    return "\n".join(lines), [call], [rows]


def _data_answer(registry: ToolRegistry):
    profile, call = _invoke(registry, "profile_dataset")
    lines = [
        f"**{profile['dataset_id']}** — {profile['source']}.",
        "",
        f"- {profile['rows']} readings across {profile['equipment_count']} pieces of equipment",
        f"- Histories run {profile['cycles_min']} to {profile['cycles_max']} cycles "
        f"(median {profile['cycles_median']:.1f})",
        f"- {len(profile['fault_eligible_channels'])} channels vary and are eligible for "
        f"fault testing; {len(profile['constant_channels'])} never change",
        f"- Data hash {profile['data_hash']}",
    ]
    if profile["positive_label_fraction"] is not None:
        lines.append(f"- {profile['positive_label_fraction']:.1%} of scorable cycles fall inside the warning horizon")

    blockers = [f for f in profile["findings"] if f["severity"] == "blocker"]
    warnings = [f for f in profile["findings"] if f["severity"] == "warning"]
    if blockers:
        lines.append("\n**Cannot be evaluated as configured:**")
        lines.extend(f"- {f['message']}" for f in blockers)
    elif warnings:
        lines.append("\n**Worth knowing:**")
        lines.extend(f"- {f['message']}" for f in warnings)
    else:
        lines.append("\nNo blocking quality problems were found.")
    return "\n".join(lines), [call], [profile]
