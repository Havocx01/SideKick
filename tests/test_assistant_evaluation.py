"""The usefulness rubric must detect regressions even with valid claim IDs."""
from pathlib import Path
import importlib.util
import asyncio

from app.assistant.investigation import EvidenceTools
from app.assistant.schemas import AnalysisRequest
from app.evidence.bundle import load_bundle


def evaluator():
    path = Path(__file__).resolve().parents[1] / "scripts/evaluate_assistant.py"
    spec = importlib.util.spec_from_file_location("assistant_evaluator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rubric_rejects_empty_valid_id_claims_generic_checks_and_wrong_scope():
    module = evaluator()
    bundle = load_bundle(Path(__file__).resolve().parents[1] / "evidence/bundle.json")
    context = AnalysisRequest(task="investigate", candidates=["logistic_regression/lr2"])
    local = EvidenceTools(bundle, context).local()
    expected = {"limits", "detection", "loss"}
    assert all(module.score(local, expected, context, local).values())
    changed = local.model_copy(deep=True)
    changed.assessment[1].text = "Please review the results."
    changed.actions = [action for action in changed.actions if not action.id.startswith("inspect-")]
    changed.sources[0].candidate = "other/private-model"
    score = module.score(changed, expected, context, local)
    assert score["required_insights_present"]  # Identifier compliance alone is insufficient.
    assert not score["essential_facts_retained"]
    assert not score["concrete_next_check_retained"]
    assert not score["scope_correct"]
    assert module.added_value(local, local)["conclusion"].startswith("No added")


def test_rubric_checks_duplicate_content_and_saved_brief_next_check():
    module = evaluator()
    bundle = load_bundle(Path(__file__).resolve().parents[1] / "evidence/bundle.json")
    context = AnalysisRequest(task="brief", candidates=["logistic_regression/lr2"])
    local = EvidenceTools(bundle, context).local()
    changed = local.model_copy(deep=True)
    changed.assessment[2].text = changed.assessment[1].text
    changed.brief_draft = "A review with no concrete check."
    checks = module.score(changed, {"limits", "detection", "loss"}, context, local)
    assert not checks["no_duplicate_assessments"]
    assert not checks["brief_retains_next_check"]


def test_provider_failure_reports_safe_fallback_separately_from_success(monkeypatch):
    module = evaluator()

    def cases(bundle, workspace):
        context = AnalysisRequest(task="investigate", candidates=["logistic_regression/lr2"])
        return [("fixture failure", EvidenceTools(bundle, context), {"limits", "detection", "loss"})]

    async def fail(*args, **kwargs):
        raise RuntimeError("fixture provider failure")

    monkeypatch.setattr(module, "cases", cases)
    monkeypatch.setattr(module, "enhance_analysis", fail)
    result = asyncio.run(module.evaluate(True, []))
    item = result["cases"][0]
    assert item["status"] == "safe_fallback" and not item["passed"]
    assert item["request_count"] == 0
    assert "median imputation" in item["next_check"]
    assert result["no_training_jobs"] and result["evidence_unchanged"]
