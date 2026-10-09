"""Practical analysis checks, beyond merely accepting valid evidence references."""
from pathlib import Path

import pytest

from app.assistant.investigation import EvidenceTools
from app.assistant.schemas import AnalysisRequest
from app.evidence.bundle import load_bundle
from app.schemas import Partition


@pytest.fixture
def bundle():
    return load_bundle(Path(__file__).resolve().parents[1] / "evidence/bundle.json")


def test_failure_explains_requirement_gap_and_specific_next_check(bundle):
    result = EvidenceTools(bundle, AnalysisRequest(task="investigate", candidates=["logistic_regression/lr2"])).local()
    answer = " ".join(claim.text for claim in result.assessment)
    assert "51.25%" in answer and "70%" in answer
    assert "15 more histories" in answer
    assert "39 fewer timely warnings" in answer
    assert "missing-reading" in result.actions[0].detail.lower()
    assert "sensor_8" in result.actions[0].detail


def test_passing_case_explains_margin_without_approving_deployment(bundle):
    result = EvidenceTools(bundle, AnalysisRequest(task="investigate", candidates=["xgboost_augmented/aug3"])).local()
    answer = " ".join(claim.text for claim in result.assessment)
    assert "percentage points above" in answer
    assert "fresh" in answer.lower()
    assert len(result.assessment) <= 3


@pytest.mark.parametrize("rul,phase", [(60, "before"), (20, "within"), (5, "too late")])
def test_warning_explains_current_phase_and_whole_history_outcome(bundle, rul, phase):
    series = next(s for s in bundle.replay_series if s.partition.value == "out_of_fold" and s.points)
    point = series.points[0]
    point.rul = rul
    context = AnalysisRequest(task="warning", candidates=[f"{series.candidate.value}/{series.config_id}"],
        scenario_id=series.scenario_id, equipment_id=series.equipment_id, cycle=point.cycle)
    result = EvidenceTools(bundle, context).local()
    answer = " ".join(claim.text for claim in result.assessment)
    assert phase in answer.lower()
    assert "10–30" in answer
    assert any(claim.id == "warning-outcome" for claim in result.assessment)
    assert not any(claim.id.startswith("limits-") for claim in result.assessment)


def test_comparison_names_qualifying_model_and_covers_alarm_tradeoff(bundle):
    result = EvidenceTools(bundle, AnalysisRequest(task="compare", candidates=["logistic_regression/lr2", "xgboost/xgb1"])).local()
    answer = " ".join(claim.text for claim in result.assessment)
    assert "XGBoost" in answer
    assert "early-alarm" in answer
    assert "statistical superiority" in answer


def test_different_case_sets_do_not_report_an_improvement(bundle):
    bundle.scenario_results = [r for r in bundle.scenario_results if not (
        r.config_id == "xgb1" and r.partition.value == "out_of_fold" and r.scenario_id == bundle.development_selection.ranked[0].worst_scenario_id)]
    result = EvidenceTools(bundle, AnalysisRequest(task="compare", candidates=["logistic_regression/lr2", "xgboost/xgb1"])).local()
    answer = " ".join(claim.text for claim in result.assessment)
    assert "coverage" in answer.lower()
    assert "comparison-warning-counts" not in [claim.id for claim in result.assessment]


def test_brief_is_a_decision_summary_without_repeated_metric_inventory(bundle):
    result = EvidenceTools(bundle, AnalysisRequest(task="brief", candidates=["logistic_regression/lr2"])).local()
    draft = result.brief_draft
    assert "Review focus" in draft and "Proposed next checks" in draft
    assert "15 more histories" in draft
    assert "deployment approval" in draft
    assert len(draft) < 2500


def test_cloud_catalog_uses_aliases_even_when_display_claims_name_faults(bundle):
    tools = EvidenceTools(bundle, AnalysisRequest(task="investigate", candidates=["logistic_regression/lr2"]))
    tools.local()
    packet = str(tools.claim_catalog())
    assert "sensor_" not in packet and "Logistic regression" not in packet and "href" not in packet
    assert "detection-model-1" in packet


def test_inconsistent_counts_do_not_create_an_invented_target_count(bundle):
    tools = EvidenceTools(bundle, AnalysisRequest(task="investigate", candidates=["logistic_regression/lr2"]))
    row = min(tools.rows, key=lambda row: row.metrics.detection_fraction)
    row.metrics.detected = 80
    packet = tools.call("list_fault_cases", {"model": "model-1", "order": "failed", "limit": 1})
    tools.call("inspect_fault_case", {"model": "model-1", "case": packet["cases"][0]["case"]})
    assert not any("more histories" in claim.text for claim in tools.claims.values())


@pytest.mark.parametrize("passing", [True, False])
def test_final_validation_explains_the_next_stage_without_reusing_scored_histories(bundle, passing):
    # Explicit fixture final evaluation; no holdout is scored by the test.
    bundle.final_evaluation = bundle.development_selection.model_copy(deep=True)
    bundle.final_evaluation.partition = Partition.holdout
    bundle.scenario_results += [row.model_copy(update={"partition": Partition.holdout})
        for row in bundle.scenario_results if row.partition == Partition.out_of_fold]
    verdict = next(v for v in bundle.final_evaluation.ranked if v.qualifies == passing)
    key = f"{verdict.candidate.value}/{verdict.config_id}"
    result = EvidenceTools(bundle, AnalysisRequest(task="investigate", candidates=[key], partition=Partition.holdout)).local()
    answer = " ".join(claim.text for claim in result.assessment)
    assert "supervised equipment pilot" in answer if passing else "already been scored" in answer
    assert "locked-model evaluation on fresh reserved histories" not in answer
    assert all(source.partition == Partition.holdout for source in result.sources)
