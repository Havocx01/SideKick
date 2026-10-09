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
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.assistant.data_review import DataTools, reviewData
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


def score(result, expected):
    ids = [claim.id for claim in result.assessment]
    refs = {source.id for source in result.sources}
    return {
        "references_resolve": all(claim.source_ids and set(claim.source_ids) <= refs for claim in result.assessment),
        "required_insights_present": all(any(id == prefix or id.startswith(prefix + "-") for id in ids) for prefix in expected),
        "concise": 0 < len(ids) <= 3,
        "brief_concise": result.brief_draft is None or len(result.brief_draft) < 3000,
    }


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
            try:
                result = (await asyncio.wait_for(enhance_analysis(tools.result, tools.context, settings, tools=tools), settings.assistant_timeout_seconds)
                          if live else tools.local())
                checks = score(result, expected)
                report.append({"case": name, "task": tools.context.task, "passed": all(checks.values()), "checks": checks,
                    "claims": [claim.model_dump() for claim in result.assessment],
                    "next_check": result.actions[0].detail if result.actions else None,
                    "tools": [call.name for call in result.investigation]})
            except Exception as error:
                report.append({"case": name, "task": tools.context.task, "passed": False,
                    "error": provider_failure(error) if not isinstance(error, ValueError) else str(error)})
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
