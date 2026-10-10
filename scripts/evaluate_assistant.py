"""Evaluate every assistant task for usefulness without training or changing evidence.

Offline by default. --live explicitly enables provider calls with the server's .env.
CSV fixtures use a temporary workspace; no uploaded data or training jobs are used.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.assistant.data_review import DataTools, reviewData
from app.assistant import agent
from app.assistant.investigation import EvidenceTools, PROMPT_VERSION
from app.assistant.provider import enhance_analysis
from app.assistant.schemas import AnalysisRequest
from app.assistant.service import provider_failure
from app.config import get_settings
from app.data.synthetic import SYNTHETIC_SENSORS, make_synthetic_dataset
from app.evidence.bundle import load_bundle
from app.experiments.datasets import register
from app.experiments.store import Workspace


def cases(bundle, workspace):
    """Recorded outcomes plus missing-evidence and CSV-quality fixtures."""
    ranked = bundle.development_selection.ranked
    passing = next(v for v in ranked if v.qualifies)
    failing = next(v for v in ranked if not v.qualifies)
    def key(v):
        return f"{v.candidate.value}/{v.config_id}"
    requests = [
        ("failing result", AnalysisRequest(task="investigate", candidates=[key(failing)]), {"limits", "detection", "loss"}),
        ("passing result", AnalysisRequest(task="investigate", candidates=[key(passing)]), {"limits", "passed"}),
        ("pass versus fail", AnalysisRequest(task="compare", candidates=[key(failing), key(passing)]), {"comparison-limits", "comparison-warning-counts", "comparison-tradeoff"}),
        ("two passing models", AnalysisRequest(task="compare", candidates=[key(v) for v in ranked if v.qualifies][:2]), {"comparison-limits", "comparison-warning-counts", "comparison-tradeoff"}),
        ("result brief", AnalysisRequest(task="brief", candidates=[key(failing)]), {"limits", "detection", "loss"}),
        ("comparison brief", AnalysisRequest(task="brief", candidates=[key(failing), key(passing)]), {"comparison-limits", "comparison-warning-counts", "comparison-tradeoff"}),
    ]
    series = next(s for s in bundle.replay_series if s.partition.value == "out_of_fold" and s.points
                  and any(p.alert for p in s.points) and any(not p.alert for p in s.points))
    for name, point in [("active warning", next(p for p in series.points if p.alert)),
                        ("inactive warning", next(p for p in series.points if not p.alert))]:
        requests.append((name, AnalysisRequest(task="warning", candidates=[f"{series.candidate.value}/{series.config_id}"],
            scenario_id=series.scenario_id, equipment_id=series.equipment_id, cycle=point.cycle), {"warning-state", "warning-outcome"}))
    requests.append(("missing replay cycle", requests[-1][1].model_copy(update={"cycle": 999999}), {"warning-unavailable", "warning-outcome"}))
    found = [(name, EvidenceTools(bundle, context), expected) for name, context, expected in requests]
    frame = make_synthetic_dataset(n_equipment=30, min_life=100, max_life=160).frame
    for name, variant in [("ready data", frame), ("unknown failure labels", frame.drop(columns=["failure_cycle"])),
                          ("missing sensor readings", frame.copy())]:
        if name == "missing sensor readings":
            variant.loc[variant.index[::10], SYNTHETIC_SENSORS[0]] = float("nan")
        id = str(uuid4())
        path = workspace.directory("datasets", id) / "data.csv"
        path.parent.mkdir(parents=True)
        variant.to_csv(path, index=False)
        record = register(workspace, path, id, "evaluation.csv")
        context = AnalysisRequest(task="data", dataset_id=id, mapping=record.mapping)
        result, descriptors, columns = reviewData(workspace, context)
        expected = {"data-readiness", "mapping-review"}
        if name == "missing sensor readings":
            expected.add("data-issue-data-missing_values")
        found.append((name, DataTools(result, context, descriptors, columns), expected))
    return found


def score(result, expected, context=None, local=None):
    ids = [claim.id for claim in result.assessment]
    refs = {source.id for source in result.sources}
    texts = [" ".join(claim.text.split()).casefold() for claim in result.assessment]
    action = result.actions[0] if result.actions else None
    check = action.detail.casefold() if action else ""
    fault_check = not local or not local.actions or not local.actions[0].id.startswith("inspect-") or bool(
        action and action.id.startswith("inspect-"))
    if "dropout" in check:
        fault_check = fault_check and all(fact in check for fact in (
            "missing-reading flags", "median imputation", "late and missed warnings"))
    essential = {
        "limits": ("recorded test limits", "fault cases"),
        "detection": ("warned in time", "requirement"),
        "loss": ("fewer timely", "simulated sensor fault", "physical failure cause"),
        "passed": ("percentage points", "early-alarm", "fresh equipment"),
        "comparison-limits": ("recorded", "validation"),
        "comparison-warning-counts": ("timely warnings", "faults can differ", "descriptive comparison"),
        "comparison-tradeoff": ("early-alarm", "statistical superiority", "deployment approval"),
        "warning-state": ("stored warning", "cycles before failure", "useful window"),
        "warning-outcome": ("history outcome", "full trace"),
        "warning-unavailable": ("unavailable", "cannot be reconstructed"),
        "data-readiness": ("training",),
        "mapping-review": ("roles",),
        "data-issue-data-missing_values": ("missing readings", "training medians"),
    }
    facts_retained = all(any((claim.id == prefix or claim.id.startswith(prefix + "-")) and
        all(fact in claim.text.casefold() for fact in essential.get(prefix, ())) for claim in result.assessment) for prefix in expected)
    return {
        "references_resolve": all(claim.source_ids and set(claim.source_ids) <= refs for claim in result.assessment),
        "required_insights_present": all(any(id == prefix or id.startswith(prefix + "-") for id in ids) for prefix in expected),
        "essential_facts_retained": facts_retained,
        "concise": 0 < len(ids) <= 3,
        "brief_concise": result.brief_draft is None or len(result.brief_draft) < 3000,
        "scope_correct": context is None or all(source.partition == context.partition and
            (context.task == "data" or source.candidate in context.candidates) for source in result.sources),
        "no_duplicate_assessments": len(texts) == len(set(texts)),
        "concrete_next_check_retained": fault_check,
        "brief_retains_next_check": result.brief_draft is None or action is None or (
            result.brief_draft.count(action.detail) == 1),
    }


class RequestMeter:
    """Count actual SDK requests, including failed ones, without logging inputs."""
    def __init__(self):
        self.count = 0
        self.original = agent.AsyncOpenAI

    def client(self, **kwargs):
        meter = self
        client = self.original(**kwargs)

        class Responses:
            async def create(self, **params):
                meter.count += 1
                return await client.responses.create(**params)

            async def parse(self, **params):
                meter.count += 1
                return await client.responses.parse(**params)

        class Client:
            responses = Responses()

            async def __aenter__(self):
                await client.__aenter__()
                return self

            async def __aexit__(self, *args):
                return await client.__aexit__(*args)

        return Client()


def added_value(result, local):
    """Report observed differences; reordered server facts aren't new facts."""
    local_claims = {claim.id: claim.text for claim in local.assessment}
    claims = {claim.id: claim.text for claim in result.assessment}
    local_action = local.actions[0].detail if local.actions else None
    action = result.actions[0].detail if result.actions else None
    return {"claims_changed": claims != local_claims, "next_check_changed": action != local_action,
            "assessment_order_changed": [claim.id for claim in result.assessment] != [claim.id for claim in local.assessment],
            "conclusion": "No added visible information over evidence-only output" if claims == local_claims and action == local_action
                else "Different verified focus; engineering usefulness still needs human assessment"}


async def evaluate(live, selected):
    settings = get_settings()
    bundle = load_bundle(settings.bundle_path)
    original = bundle.model_dump_json()
    report = []
    with tempfile.TemporaryDirectory(prefix="sidekick-assistant-eval-") as directory:
        workspace = Workspace(Path(directory))
        for name, tools, expected in cases(bundle, workspace):
            if selected and name not in selected:
                continue
            meter = RequestMeter()
            local_started = time.perf_counter()
            local = tools.fresh().local()
            local_seconds = time.perf_counter() - local_started
            started = time.perf_counter()
            try:
                if live:
                    agent.AsyncOpenAI = meter.client
                result = (await asyncio.wait_for(enhance_analysis(tools.result, tools.context, settings, tools=tools), settings.assistant_timeout_seconds)
                          if live else local)
                checks = score(result, expected, tools.context, local)
                fixed = tools.context.task in ("compare", "warning", "data") or (
                    tools.context.task == "brief" and (tools.context.equipment_id or len(tools.context.candidates) == 2))
                if live:
                    checks["request_budget_respected"] = meter.count == 1 if fixed else meter.count <= 9
                successful_ai = live and result.mode == "ai"
                status = "successful_ai" if successful_ai else "safe_fallback" if live else "evidence_only"
                report.append({"case": name, "task": tools.context.task, "passed": all(checks.values()) and (not live or successful_ai),
                    "status": status, "checks": checks, "request_count": meter.count,
                    "latency_seconds": time.perf_counter() - started if live else local_seconds, "local_seconds": local_seconds,
                    "added_value_vs_local": added_value(result, local),
                    "claims": [claim.model_dump() for claim in result.assessment],
                    "next_check": result.actions[0].detail if result.actions else None,
                    "tools": [call.name for call in result.investigation]})
            except Exception as error:
                fallback_checks = score(local, expected, tools.context, local)
                report.append({"case": name, "task": tools.context.task, "passed": False,
                    "status": "safe_fallback" if all(fallback_checks.values()) else "unsafe_fallback",
                    "checks": fallback_checks, "request_count": meter.count, "latency_seconds": time.perf_counter() - started,
                    "local_seconds": local_seconds, "claims": [claim.model_dump() for claim in local.assessment],
                    "next_check": local.actions[0].detail if local.actions else None,
                    "error": provider_failure(error) if not isinstance(error, ValueError) else str(error)})
            finally:
                agent.AsyncOpenAI = meter.original
        with workspace.connect() as db:
            no_training = db.execute("SELECT COUNT(*) FROM experiments").fetchone()[0] == 0
    return {"mode": "live" if live else "offline", "model": settings.assistant_model if live else None,
        "prompt_version": PROMPT_VERSION, "evidence_unchanged": bundle.model_dump_json() == original,
        "no_training_jobs": no_training, "cases": report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--case", action="append", default=[], help="Evaluate only named cases; repeat to select several.")
    parser.add_argument("--output", type=Path, help="Save the full rubric and answers as JSON.")
    args = parser.parse_args()
    live = args.live or os.environ.get("SIDEKICK_ASSISTANT_LIVE_EVAL") == "1"
    if live:
        from dotenv import load_dotenv
        load_dotenv(REPO_ROOT / ".env")
        if not get_settings().openai_api_key:
            print("Configure OPENAI_API_KEY in the server environment or .env to run live evaluation.")
            return 2
    result = asyncio.run(evaluate(live, args.case))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({**result, "cases": [{k: v for k, v in item.items() if k not in ("claims", "tools", "next_check")}
                                        for item in result["cases"]]}, indent=2))
    return 0 if result["cases"] and all(item["passed"] for item in result["cases"]) and result["evidence_unchanged"] and result["no_training_jobs"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
