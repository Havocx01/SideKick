from pathlib import Path

import pytest

from app.assistant.investigation import EvidenceTools
from app.assistant.schemas import AnalysisRequest
from app.evidence.bundle import load_bundle


@pytest.fixture
def tools():
    bundle = load_bundle(Path(__file__).resolve().parents[1] / "evidence/bundle.json")
    context = AnalysisRequest(task="investigate", candidates=["logistic_regression/lr2"])
    return EvidenceTools(bundle, context)


def test_case_inspection_has_exact_metrics_and_verified_claims(tools):
    packet = tools.call("list_fault_cases", {"model": "model-1", "order": "failed", "limit": 3})
    case = packet["cases"][0]
    inspected = tools.call("inspect_fault_case", {"model": "model-1", "case": case["case"]})
    assert inspected["metrics"]["detected"] == 41
    assert inspected["metrics"]["engines"] == 80
    assert inspected["meets_limits"] is False
    assert inspected["claims"]
    result = tools.finish(inspected["finding_ids"], inspected["claims"], None, "test")
    assert all(claim.source_ids for claim in result.assessment)
    assert "39" in " ".join(claim.text for claim in result.assessment)
    assert all(source.partition == tools.context.partition for source in result.sources)
    assert all(source.candidate == "logistic_regression/lr2" for source in result.sources)


@pytest.mark.parametrize("name,args", [
    ("train_model", {}),
    ("get_model_metrics", {"model": "xgboost/secret"}),
    ("get_model_metrics", {"model": "model-1", "partition": "holdout"}),
    ("inspect_fault_case", {"model": "model-1", "case": "case-999"}),
    ("list_fault_cases", {"model": "model-1", "order": "failed", "limit": 500}),
])
def test_unavailable_tools_and_out_of_scope_arguments_are_rejected(tools, name, args):
    with pytest.raises(ValueError):
        tools.call(name, args)


def test_cloud_packets_exclude_identity_and_raw_sensor_values(tools):
    packet = tools.call("list_fault_cases", {"model": "model-1", "order": "weakest_detection", "limit": 2})
    text = str(packet)
    assert "sensor_" not in text and "logistic_regression" not in text
    assert "equipment_id" not in text and "data.csv" not in text
    assert "href" not in text


def test_final_selection_must_reference_evidence_actually_inspected(tools):
    with pytest.raises(ValueError, match="inspected"):
        tools.finish(["f0"], [], None, "test")
    packet = tools.call("get_model_metrics", {"model": "model-1"})
    with pytest.raises(ValueError):
        tools.finish(packet["finding_ids"], ["invented-claim"], None, "test")


def test_comparison_and_warning_preserve_exact_context():
    bundle = load_bundle(Path(__file__).resolve().parents[1] / "evidence/bundle.json")
    context = AnalysisRequest(task="compare", candidates=["logistic_regression/lr2", "xgboost/xgb1"])
    result = EvidenceTools(bundle, context).local()
    assert "38 more timely warnings" in " ".join(claim.text for claim in result.assessment)
    assert "faults can differ" in " ".join(claim.text for claim in result.assessment)
    sourceIds = {source.id for source in result.sources}
    assert all(set(claim.source_ids) <= sourceIds for claim in result.assessment)
    replay = next(series for series in bundle.replay_series if series.partition.value == "out_of_fold" and series.points)
    context = AnalysisRequest(task="warning", candidates=[f"{replay.candidate.value}/{replay.config_id}"], scenario_id=replay.scenario_id,
        equipment_id=replay.equipment_id, cycle=replay.points[0].cycle)
    tools = EvidenceTools(bundle, context)
    packet = tools.call("get_warning_events", {})
    result = tools.finish(packet["finding_ids"][:3], packet["claims"], "replay", None)
    assert result.assessment[0].id == "warning-state"
    assert any(source.cycle == replay.points[0].cycle for source in result.sources)
    assert "equipment_id" not in str(packet) and "sensor_clean" not in str(packet)


def test_missing_replay_keeps_only_an_unavailable_warning_claim():
    bundle = load_bundle(Path(__file__).resolve().parents[1] / "evidence/bundle.json")
    context = AnalysisRequest(task="warning", candidates=["logistic_regression/lr2"], scenario_id="clean", equipment_id="unavailable", cycle=100)
    tools = EvidenceTools(bundle, context)
    result = tools.local()
    assert result.assessment[0].id == "warning-unavailable" and result.assessment[0].source_ids


def test_review_briefs_preserve_comparison_and_replay_contexts():
    bundle = load_bundle(Path(__file__).resolve().parents[1] / "evidence/bundle.json")
    context = AnalysisRequest(task="brief", candidates=["logistic_regression/lr2", "xgboost/xgb1"])
    result = EvidenceTools(bundle, context).local()
    assert result.findings[0].title == "Comparison overview"
    assert "descriptive comparison" in result.brief_draft
    replay = next(series for series in bundle.replay_series if series.partition.value == "out_of_fold" and series.points)
    context = AnalysisRequest(task="brief", candidates=[f"{replay.candidate.value}/{replay.config_id}"], scenario_id=replay.scenario_id,
        equipment_id=replay.equipment_id, cycle=replay.points[0].cycle)
    result = EvidenceTools(bundle, context).local()
    assert result.assessment[0].id == "warning-state"
    assert result.actions[0].id == "replay"
    assert any(call.name == "get_warning_events" for call in result.investigation)
    assert "History outcome" in result.brief_draft or "Recorded warning" in result.brief_draft
