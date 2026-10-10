"""Prepare an offline, printable engineer review packet without AI or training.

The packet separates reviewer evidence, deterministic output, and facilitator
answers. It does not claim an engineer study has happened or fabricate AI output.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import sys
import tempfile
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.assistant.data_review import DataTools, reviewData
from app.assistant.evidence import with_brief
from app.assistant.investigation import EvidenceTools, PROMPT_VERSION
from app.assistant.schemas import AnalysisRequest
from app.data.synthetic import SYNTHETIC_SENSORS, make_synthetic_dataset
from app.evidence.bundle import load_bundle
from app.experiments.datasets import register
from app.experiments.store import Workspace

PACK_VERSION = 1
METHOD_ORDERS = [
    ["manual", "local", "ai"],
    ["local", "ai", "manual"],
    ["ai", "manual", "local"],
]
QUESTION = "What is the justified next action? Cite the decisive evidence, its scope, and what this evidence does not establish."
STATUS = "Prepared offline; no engineer sessions conducted. AI responses are not included."
NEXT_CHECK_CRITERIA = {
    "C01": "Review the weakest recorded fault and confirm coverage; use genuinely fresh reserved histories for any locked-model final check.",
    "C02": "Check missing-reading flags and median imputation, then inspect late and missed warnings for the decisive dropout case before retesting.",
    "C03": "Review failed fault cases and coverage; advance a qualifying candidate only to a fresh validation check, without claiming statistical superiority.",
    "C04": "Review detection, early-alarm burden and required-case coverage together; weakest cases can differ and small differences do not prove superiority.",
    "C05": "Inspect the stored warning at the selected cycle and the complete history outcome before deciding on an equipment action.",
    "C06": "Inspect later warning events and the whole-history outcome; absence of a warning at this early cycle is not proof of a missed history.",
    "C07": "Abstain on the unavailable cycle's warning state; select an actually recorded cycle before interpreting that state.",
    "C08": "Inspect healthy early-warning episodes and their eligible-cycle denominator against the recorded maximum; resolve the alarm-limit failure before validation.",
    "C09": "Confirm column roles and observed failure records with the equipment owner before training.",
    "C10": "Obtain genuine failure-cycle labels or owner confirmation that all histories reach failure; do not manufacture labels from last readings.",
    "C11": "Check missingness and the training-median/flag handling, then confirm roles and observed failure records; readiness does not establish fault robustness.",
    "C12": "Resolve duplicate equipment/cycle pairs using the original records, retain one correct reading per pair, and validate again.",
}


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def encoded(value) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def key(verdict) -> str:
    return f"{verdict.candidate.value}/{verdict.config_id}"


def _cases(bundle, workspace):
    """Generate supported contexts; fixture changes never modify recorded evidence."""
    passing = [row for row in bundle.development_selection.ranked if row.qualifies]
    failing = [row for row in bundle.development_selection.ranked if not row.qualifies]
    if len(passing) < 2 or not failing:
        raise ValueError("The review bundle needs two passing models and one failing model.")
    criteria = bundle.development_selection.criteria
    if criteria.max_early_alarm_burden > 0.95:
        raise ValueError("The excessive-alarm fixture needs a recorded maximum of at most 95% to exceed it by five percentage points.")
    # The fixed facilitator rubric addresses dropout detection, not an arbitrary
    # failed candidate. Select the same decisive case that local inspection uses.
    detection_failure = None
    for verdict in reversed(failing):
        tools = EvidenceTools(bundle, AnalysisRequest(task="investigate", candidates=[key(verdict)]))
        failed_rows = sorted((row for row in tools.rows if not tools.passes(row)),
                             key=lambda row: (row.metrics.detection_fraction, row.scenario_id))
        if (failed_rows and failed_rows[0].fault.kind.value == "dropout"
                and failed_rows[0].metrics.detection_fraction < criteria.min_detection_fraction):
            detection_failure = verdict
            break
    if detection_failure is None:
        raise ValueError("The detection-failure case needs a failing model whose decisive recorded fault is dropout below the detection minimum.")

    replay_selection = None
    for series in bundle.replay_series:
        active_points = [point for point in series.points if point.alert]
        if series.partition.value != "out_of_fold" or not active_points:
            continue
        first_active = min(active_points, key=lambda point: point.cycle)
        early_inactive = [point for point in series.points if not point.alert
                          and point.cycle < first_active.cycle and point.rul > criteria.horizon_cycles]
        if early_inactive:
            replay_selection = (series, first_active, min(early_inactive, key=lambda point: point.cycle))
            break
    if replay_selection is None:
        raise ValueError("The review bundle needs an inactive replay cycle before its first active warning and before the useful warning window.")
    results = []

    def evidence(id, title, question, context, source=bundle, fixture=None):
        result = EvidenceTools(source, context).local()
        raw = {"config": source.config, "criteria": source.development_selection.criteria.model_dump(mode="json"),
               "holdout_status": source.holdout_status}
        if context.task == "warning":
            series = next((series for series in source.replay_series if series.partition == context.partition
                           and key(series) in context.candidates and series.scenario_id == context.scenario_id
                           and series.equipment_id == context.equipment_id), None)
            raw["replay"] = None if not series else {
                **series.model_dump(mode="json", exclude={"points"}),
                "selected_cycle": context.cycle,
                "selected_point": next((point.model_dump(mode="json") for point in series.points
                                        if point.cycle == context.cycle), None),
            }
        brief_context = context.model_copy(update={"task": "brief"})
        brief = with_brief(result, brief_context).brief_draft
        results.append({"id": id, "title": title, "question": question + " " + QUESTION,
                        "kind": "synthetic protocol fixture" if fixture else "historical recorded benchmark",
                        "fixture": fixture, "context": context.model_dump(mode="json"), "raw": raw,
                        "brief_example": {"context": brief_context.model_dump(mode="json"), "text": brief,
                                          "origin": "Deterministic conversion of this exact analysis; no new analysis job."},
                        "result": result.model_dump(mode="json")})

    evidence("C01", "Passing model", "Does this result justify advancing to a final check?",
             AnalysisRequest(task="investigate", candidates=[key(passing[0])]))
    evidence("C02", "Detection failure", "Which requirement prevents this model advancing?",
             AnalysisRequest(task="investigate", candidates=[key(detection_failure)]))
    evidence("C03", "Pass versus fail", "Which candidate meets the recorded limits, and what comparison is justified?",
             AnalysisRequest(task="compare", candidates=[key(detection_failure), key(passing[0])]))
    evidence("C04", "Two qualifying candidates", "What tradeoff matters before choosing between these candidates?",
             AnalysisRequest(task="compare", candidates=[key(row) for row in passing[:2]]))
    series, active_point, inactive_point = replay_selection
    for id, title, point in [
        ("C05", "Active warning", active_point),
        ("C06", "Inactive warning", inactive_point),
        ("C07", "Unavailable replay cycle", None),
    ]:
        evidence(id, title, "What does the selected cycle say, and how does it relate to the whole-history outcome?",
                 AnalysisRequest(task="warning", candidates=[key(series)], scenario_id=series.scenario_id,
                                 equipment_id=series.equipment_id,
                                 cycle=point.cycle if point else max(point.cycle for point in series.points) + 1))

    # Explicit simulated evidence fixture: the unchanged historical result is
    # never relabelled. Only a private copy has a deliberately breached limit.
    alarm = bundle.model_copy(deep=True)
    row = next(row for row in alarm.development_selection.ranked if key(row) == key(passing[0]))
    row.clean.early_alarm_burden = alarm.development_selection.criteria.max_early_alarm_burden + 0.05
    row.passes_clean = False
    row.qualifies = False
    alarm.development_selection.recommended = None
    evidence("C08", "Excessive early alarms", "Does good detection overcome a failed early-alarm limit?",
             AnalysisRequest(task="investigate", candidates=[key(row)]), alarm,
             "Private copied fixture: healthy early-alarm burden is set five percentage points above the recorded maximum; "
             "qualification is false. Other recorded fault outcomes are retained. No model was trained or scored.")

    frame = make_synthetic_dataset(n_equipment=30, min_life=100, max_life=160, seed=20260918).frame
    variants = [("C09", "Ready data", frame.copy()),
                ("C10", "Unconfirmed failure labels", frame.drop(columns=["failure_cycle"])),
                ("C11", "Missing sensor readings", frame.copy()),
                ("C12", "Duplicate equipment cycles", frame.copy())]
    variants[2][2].loc[frame.index[::10], SYNTHETIC_SENSORS[0]] = float("nan")
    variants[3][2].loc[len(frame)] = frame.iloc[0]
    for id, title, data in variants:
        dataset_id = str(uuid5(NAMESPACE_URL, f"sidekick-engineer-evaluation-v{PACK_VERSION}/{id}"))
        path = workspace.directory("datasets", dataset_id) / "data.csv"
        path.parent.mkdir(parents=True)
        data.to_csv(path, index=False)
        record = register(workspace, path, dataset_id, f"{id}.csv")
        context = AnalysisRequest(task="data", dataset_id=dataset_id, mapping=record.mapping)
        review, descriptors, columns = reviewData(workspace, context)
        result = DataTools(review, context, descriptors, columns).local()
        results.append({"id": id, "title": title,
                        "question": "Is this CSV ready for mapping confirmation and training? " + QUESTION,
                        "kind": "generated synthetic CSV", "fixture": "Seed 20260918; 30 simulated complete histories, "
                        "100–160 cycles. This is a file-validation exercise, not measured equipment performance.",
                        "context": context.model_dump(mode="json"),
                        "raw": {"columns": record.columns, "row_count": record.row_count, "preview": record.preview,
                                "suggested_mapping": record.mapping.model_dump(mode="json") if record.mapping else None,
                                "file_sha256": digest(path.read_bytes()), "csv": f"evidence/{id}.csv"},
                        "csv_bytes": path.read_bytes(), "result": result.model_dump(mode="json")})
    return results


def _text(value) -> str:
    return html.escape(str(value), quote=True)


def _page(title, content):
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>{_text(title)}</title>
<style>body{{margin:0;background:#f7f8fa;color:#20242b;font:15px/1.55 system-ui,sans-serif}}
main{{max-width:1080px;margin:32px auto;padding:0 24px}}h1{{font-size:28px}}h2{{font-size:21px}}
h3{{font-size:16px}}a{{color:#006edb}}.note{{color:#5d6877}}.status{{border-left:3px solid #0088ff;padding:8px 14px;background:#eaf3fc}}
section{{background:white;border:1px solid #dde2e8;border-radius:12px;padding:20px 24px;margin:20px 0;break-inside:avoid}}
table{{width:100%;border-collapse:collapse;margin:12px 0}}th,td{{padding:8px;text-align:left;border-bottom:1px solid #e2e6eb;vertical-align:top}}
td{{overflow-wrap:anywhere}}th{{font-size:13px;color:#5d6877}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}}
code{{overflow-wrap:anywhere}}.entry{{border-bottom:1px solid #ccd4df;height:42px}}@media(max-width:600px){{main{{padding:0 12px}}section{{padding:16px}}table{{font-size:12px}}}}
@media print{{body{{background:white;font-size:11px}}main{{margin:0;max-width:none}}section{{border-radius:0}}a{{color:inherit}}}}
</style></head><body><main><h1>{_text(title)}</h1><p class="status">{_text(STATUS)}</p>{content}</main></body></html>"""


def _case_header(case):
    fixture = f'<p class="note">{_text(case["fixture"])}</p>' if case["fixture"] else ""
    context = case["context"]
    selected = []
    if context["candidates"]:
        selected.append("Models: " + ", ".join(context["candidates"]))
        selected.append("Partition: Development (out of fold)" if context["partition"] == "out_of_fold" else "Partition: Final validation")
    for name, label in [("scenario_id", "Scenario"), ("equipment_id", "Equipment"), ("cycle", "Selected cycle")]:
        if context[name] is not None:
            selected.append(f"{label}: {context[name]}")
    if context["dataset_id"]:
        selected.append("File: " + case["id"] + ".csv · Current draft mapping; not yet confirmed")
    return (f'<h2>{_text(case["id"])} · {_text(case["title"])}</h2><p class="note">{_text(case["kind"])}</p>'
            f'{fixture}<p>{_text(case["question"])}</p><h3>Selected context</h3>'
            + "".join(f'<p class="note">{_text(value)}</p>' for value in selected))


def _raw_context(case):
    raw = case["raw"]
    if "criteria" in raw:
        criteria = raw["criteria"]
        content = (f'<p>Useful warning window: {_text(criteria["min_useful_lead"])}–{_text(criteria["horizon_cycles"])} operating cycles before failure. '
                   f'Minimum timely detection: {_text(criteria["min_detection_fraction"] * 100):s}%. '
                   f'Maximum early-alarm burden: {_text(criteria["max_early_alarm_burden"] * 100):s}%.</p>'
                   '<p class="note">Early-alarm burden is a share of eligible early cycles, not the probability a warning is false.</p>'
                   f'<p>{_text(raw["holdout_status"])}</p>')
        if "replay" in raw:
            replay = raw["replay"]
            details = None if replay is None else {name: replay[name] for name in ["selected_cycle", "selected_point", "episodes", "outcome"]}
            content += '<h3>Stored replay</h3><pre>' + _text(json.dumps(details, indent=2, ensure_ascii=False)) + '</pre>'
    else:
        content = f'<p>{_text(raw["row_count"])} readings · {_text(len(raw["columns"]))} columns.</p>'
        content += '<h3>Draft column roles</h3><pre>' + _text(json.dumps(raw["suggested_mapping"], indent=2, ensure_ascii=False)) + '</pre>'
    return content + '<details><summary>Complete recorded context</summary><pre>' + _text(json.dumps(raw, indent=2, ensure_ascii=False)) + '</pre></details>'


def _sources(case):
    rows = "".join(f'<tr><td>{_text(source["id"])}</td><td>{_text(source["label"])}</td>'
                   f'<td>{_text(source["display"])}</td><td>{_text(source["context"])}</td></tr>'
                   for source in case["result"]["sources"])
    return f'<table><thead><tr><th>Reference</th><th>Recorded measure</th><th>Value</th><th>Scope</th></tr></thead><tbody>{rows}</tbody></table>'


def _reviewer(cases, local):
    content = '<p>Review one assigned case and method at a time. Record your decision before looking at other methods or the facilitator key.</p>'
    for case in cases:
        body = _case_header(case)
        if local:
            body += '<h3>Deterministic analysis</h3>' + "".join(f'<p>{_text(claim["text"])}</p>' for claim in case["result"]["assessment"])
            body += '<h3>Next check</h3><p>' + _text(_next_check(case)) + '</p>'
            if case.get("brief_example"):
                body += '<details><summary>Deterministic review brief</summary><pre>' + _text(case["brief_example"]["text"]) + '</pre></details>'
            body += '<details><summary>Supporting recorded evidence</summary>' + _sources(case) + _raw_context(case) + '</details>'
        else:
            body += '<h3>Recorded evidence</h3>' + _sources(case)
            body += '<h3>Protocol / file context</h3>' + _raw_context(case)
        if "csv" in case["raw"]:
            body += f'<p><a href="{_text(case["raw"]["csv"])}">Open the complete synthetic CSV</a></p>'
        body += '<h3>Scope and limitations</h3><ul>' + "".join(f'<li>{_text(value)}</li>' for value in case["result"]["limitations"]) + '</ul>'
        body += '<h3>Your decision and evidence</h3><div class="entry"></div><h3>Your next check</h3><div class="entry"></div>'
        content += '<section>' + body + '</section>'
    return _page('Sidekick · ' + ('Local analysis' if local else 'Manual evidence review'), content)


def _next_check(case):
    actions = case["result"]["actions"]
    if actions:
        return actions[0]["detail"]
    # Data review has no navigation action. Its authoritative readiness claim
    # already describes the required validation/role check; do not invent one.
    return next(claim["text"] for claim in case["result"]["assessment"] if claim["id"] == "data-readiness")


def prepare(output: Path, bundle_path: Path = REPO_ROOT / "evidence/bundle.json") -> dict:
    output = output.resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Choose a new or empty output directory; existing evaluation materials are never overwritten.")
    bundle_bytes = bundle_path.read_bytes()
    bundle = load_bundle(bundle_path)
    original = bundle.model_dump_json()
    with tempfile.TemporaryDirectory(prefix="sidekick-engineer-pack-") as directory:
        workspace = Workspace(Path(directory))
        cases = _cases(bundle, workspace)
        with workspace.connect() as db:
            no_training = db.execute("SELECT COUNT(*) FROM experiments").fetchone()[0] == 0
    if not no_training or bundle.model_dump_json() != original or bundle_path.read_bytes() != bundle_bytes:
        raise RuntimeError("Evaluation preparation changed recorded evidence or created a training job.")

    files = {"reviewer/manual.html": _reviewer(cases, False).encode(),
             "reviewer/local.html": _reviewer(cases, True).encode()}
    answers = []
    for case in cases:
        if "csv_bytes" in case:
            files[f'reviewer/evidence/{case["id"]}.csv'] = case.pop("csv_bytes")
        # Full server sources and IDs remain in the private key and case receipt.
        answers.append({"case_id": case["id"], "scope": case["context"],
                        "essential_facts": case["result"]["assessment"], "local_next_check": _next_check(case),
                        "acceptable_next_check": NEXT_CHECK_CRITERIA[case["id"]],
                        "next_check_origin": "Facilitator rubric grounded in the recorded facts; engineer adjudication still required.",
                        "limitations": case["result"]["limitations"], "sources": case["result"]["sources"],
                        "evidence_digest": case["result"]["evidence_digest"],
                        "engineer_adjudicated": False})
    files["facilitator/answer-key.json"] = encoded(answers)
    files["facilitator/cases.json"] = encoded(cases)
    key_html = '<p>Facilitator only. Validate the relevance of these server-derived facts with an engineer before scored sessions. Equivalent justified answers are acceptable; do not score phrasing.</p>'
    for case, answer in zip(cases, answers, strict=True):
        key_html += '<section>' + _case_header(case) + '<h3>Essential facts</h3>'
        key_html += '<ul>' + "".join(f'<li>{_text(claim["text"])} <code>{_text(", ".join(claim["source_ids"]))}</code></li>'
                                    for claim in answer["essential_facts"]) + '</ul>'
        key_html += '<h3>Acceptable next-check criteria</h3><p>' + _text(answer["acceptable_next_check"]) + '</p>'
        key_html += '<p class="note">Facilitator rubric; engineer adjudication required. The deterministic action is assessed against this rubric, not treated as its own proof of usefulness.</p>'
        key_html += '<h3>Actual deterministic next check</h3><p>' + _text(answer["local_next_check"]) + '</p>' + _sources(case) + '</section>'
    files["facilitator/answer-key.html"] = _page("Sidekick · Facilitator answer key", key_html).encode()
    instructions = """# Prepared engineer review packet

Status: prepared offline; no engineer evaluation conducted. No training or AI requests were made. Historical and synthetic cases do not establish field reliability.

1. Agree the equipment decision, reviewer, success criteria, failure definition and data policy using docs/sidekick-engineer-evaluation.md.
2. Give the facilitator folder only to the facilitator. Have an engineer check answer-key relevance before scoring. Manual pages contain raw server evidence, not a model-generated reference answer.
3. Use reviewer/manual.html or reviewer/local.html for the assigned method. Score sheets include AI rows, but AI outputs are absent: mark those rows not_available unless separately authorized saved outputs are supplied and their context/fingerprints checked. Do not present local output as AI.
4. method-order.csv rotates the three methods across reviewers. This pack reuses contexts: do not show one reviewer the identical case under all three methods in one session. Assign independent reviewers, or use separately adjudicated equivalent cases; record familiarity and learning effects. With one engineer, report exploratory observations only.
5. Record a decision and reason, essential facts missed, specific feasible next check, scope mistakes, brief edits, review seconds and generation-wait seconds separately. A fallback is not a successful AI response. Set success criteria before inspecting results.
6. Use score-sheet.csv for observations. Leave missing observations blank; do not convert blanks into zeros. Helpful ratings are secondary to correctness. Record all exclusions, abstentions and failures.
7. The synthetic CSV IDs are isolated preparation references, not registrations in your running app. Historical benchmark links can be used with the recorded benchmark; no current personal data or saved cloud text is included.

Score anchors: next_check_quality 0=absent/generic, 1=specific but incomplete, 2=feasible and covers the key risk. brief_quality 0=wrong scope/decisive facts missing, 1=usable with substantive edits, 2=correct scope/facts/check with minor or no edits. helpfulness 1–5 requires a concrete reason. Counts and times are nonnegative observations, never automatic software scores.
"""
    files["README.md"] = instructions.encode()
    import io

    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["reviewer_id", "case_id", "method", "status", "prior_familiarity", "decision", "reason_and_source_ids",
                     "critical_misunderstandings", "essential_facts_missed", "next_check", "next_check_quality_0_2",
                     "review_seconds", "generation_wait_seconds", "brief_quality_0_2", "brief_edits_needed",
                     "helpfulness_1_5", "helpfulness_reason", "interruptions_or_exclusions"])
    for case in cases:
        for method in METHOD_ORDERS[0]:
            writer.writerow(["", case["id"], method, "not_available" if method == "ai" else "not_started"] + [""] * 14)
    files["score-sheet.csv"] = stream.getvalue().encode()
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["reviewer_cohort", "first_method", "second_method", "third_method"])
    for i, order in enumerate(METHOD_ORDERS, 1):
        writer.writerow([i, *order])
    files["method-order.csv"] = stream.getvalue().encode()
    manifest = {"pack_version": PACK_VERSION, "status": STATUS, "case_count": len(cases),
                "engineer_study_conducted": False, "provider_requests": 0, "training_jobs": 0,
                "evidence_unchanged": True, "ai_outputs_included": False, "prompt_version": PROMPT_VERSION,
                "recorded_source_digest": bundle.source_digest, "recorded_config_fingerprint": bundle.config_fingerprint,
                "recorded_git_commit": bundle.git_commit, "bundle_sha256": digest(bundle_bytes),
                "files": {name: digest(data) for name, data in sorted(files.items())}}
    files["manifest.json"] = encoded(manifest)
    # Validation and generation finish before writing output. No existing files
    # are removed or replaced, including a prior reviewer's observations.
    output.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as destination:
            destination.write(data)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "output/engineer-evaluation")
    parser.add_argument("--bundle", type=Path, default=REPO_ROOT / "evidence/bundle.json")
    args = parser.parse_args()
    try:
        manifest = prepare(args.output, args.bundle)
    except (OSError, ValueError) as failure:
        parser.exit(1, f"Cannot prepare review packet: {failure}\n")
    print(json.dumps({"output": str(args.output.resolve()), "cases": manifest["case_count"],
                      "status": manifest["status"], "provider_requests": 0, "training_jobs": 0}, indent=2))


if __name__ == "__main__":
    main()
