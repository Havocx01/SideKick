"""Small live evaluation of AI interpretation against recorded benchmark evidence.

Runs only with SIDEKICK_ASSISTANT_LIVE_EVAL=1 and a server-side OPENAI_API_KEY. Each case
sends one provider packet; rerun after changing SIDEKICK_ASSISTANT_MODEL or the prompt.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.assistant.evidence import build_analysis  # noqa: E402
from app.assistant.provider import enhance_analysis  # noqa: E402
from app.assistant.schemas import AnalysisRequest  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.evidence.bundle import load_bundle  # noqa: E402


def cases(bundle):
    ranked = bundle.development_selection.ranked
    failing = next((v for v in ranked if not v.qualifies), None)
    passing = next((v for v in ranked if v.qualifies), None)
    key = lambda v: f"{v.candidate.value}/{v.config_id}"  # noqa: E731
    found = []
    if failing:
        found.append(("investigate failure", AnalysisRequest(task="investigate", candidates=[key(failing)])))
    if passing:
        found.append(("analyze passing result", AnalysisRequest(task="investigate", candidates=[key(passing)])))
    if failing and passing:
        found.append(("compare pass and fail", AnalysisRequest(task="compare", candidates=[key(failing), key(passing)])))
    series = next((s for s in bundle.replay_series if s.partition.value == "out_of_fold" and s.episodes), None)
    if series:
        found.append(("explain warning", AnalysisRequest(task="warning", candidates=[f"{series.candidate.value}/{series.config_id}"],
                                                         scenario_id=series.scenario_id, equipment_id=series.equipment_id,
                                                         cycle=series.episodes[0].start_cycle)))
    if failing:
        found.append(("review brief", AnalysisRequest(task="brief", candidates=[key(failing)])))
    return found


async def main() -> int:
    settings = get_settings()
    if os.environ.get("SIDEKICK_ASSISTANT_LIVE_EVAL") != "1" or not settings.openai_api_key:
        print("Set SIDEKICK_ASSISTANT_LIVE_EVAL=1 and OPENAI_API_KEY to run the live evaluation.")
        return 2
    bundle = load_bundle(settings.bundle_path)
    report = []
    for name, context in cases(bundle):
        evidence = build_analysis(bundle, context)
        try:
            result = await asyncio.wait_for(enhance_analysis(evidence, context, settings), settings.assistant_timeout_seconds)
            report.append({"case": name, "verified": True, "findings": [f.id for f in result.findings[:3]],
                           "interpretation": result.interpretation})
        except Exception as error:  # Recorded so a reviewer can judge rejection rates.
            report.append({"case": name, "verified": False, "reason": str(error) or type(error).__name__})
    print(json.dumps({"model": settings.assistant_model, "prompt_version": evidence.prompt_version, "cases": report}, indent=2))
    return 0 if all(item["verified"] for item in report) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
