from pathlib import Path

import pytest

from app.evidence.bundle import load_bundle
from app.experiments.decision import decision
from app.experiments.export import render_report
from app.schemas import CandidateKind, Partition
from app.scoring.selection import build_verdict, select


@pytest.fixture
def results():
    bundle = load_bundle(Path(__file__).resolve().parents[1] / "evidence" / "bundle.json")
    rows = [r for r in bundle.scenario_results if r.candidate == CandidateKind.xgboost
            and r.config_id == "xgb1" and r.required and r.fault and r.partition == Partition.out_of_fold][:2]
    for row in rows:
        row.metrics.detection_fraction = 1
        row.metrics.detected = row.metrics.engines
        row.metrics.late = row.metrics.missed = 0
        row.metrics.early_alarm_burden = .01
        row.coverage_complete = True
    clean = rows[0].metrics.model_copy(deep=True)
    bundle.scenario_results = rows
    return bundle, rows, clean


def report_for(results, partition=Partition.out_of_fold):
    bundle, rows, clean = results
    criteria = bundle.development_selection.criteria
    verdict = build_verdict(candidate=CandidateKind.xgboost, config_id="xgb1", threshold=.5,
                            clean=clean, required=rows, criteria=criteria)
    selection = select([verdict], criteria, partition=partition)
    if partition == Partition.holdout:
        bundle.final_evaluation = selection
    else:
        bundle.development_selection = selection
    return decision(bundle, "xgboost/xgb1", partition)


def test_burden_failure_names_actual_fault_not_lowest_detection(results):
    bundle, rows, _ = results
    rows[0].metrics.detection_fraction = .8
    rows[0].metrics.detected = 64
    rows[0].metrics.missed = 16
    rows[1].metrics.early_alarm_burden = .25
    report = report_for(results)
    assert "25.00% early alarm time" in report.qualification_reason
    assert "10.0% maximum" in report.qualification_reason
    assert rows[1].fault.label() in report.qualification_reason
    assert rows[0].fault.label() not in report.qualification_reason
    assert "25.00%" in report.guide[0].answer.split(". With healthy")[0]
    fault_preview = report.guide[1].answer.split(". Healthy detection")[0]
    assert rows[0].fault.label() in fault_preview
    assert rows[1].fault.label() in fault_preview
    assert "25.00%" in fault_preview
    html, _ = render_report(bundle, "xgboost/xgb1")
    assert report.qualification_reason in html


def test_detection_and_burden_failures_are_both_explained(results):
    _, rows, _ = results
    rows[0].metrics.detection_fraction = .5
    rows[0].metrics.detected = 40
    rows[0].metrics.missed = 40
    rows[1].metrics.early_alarm_burden = .25
    report = report_for(results)
    assert "40/80" in report.qualification_reason
    assert "70.0% minimum" in report.qualification_reason
    assert rows[0].fault.label() in report.qualification_reason
    assert rows[1].fault.label() in report.qualification_reason


def test_healthy_failure_does_not_blame_a_passing_fault(results):
    _, rows, clean = results
    clean.detection_fraction = .5
    clean.detected = 40
    clean.missed = 40
    report = report_for(results)
    assert "Healthy sensors: 40/80" in report.qualification_reason
    assert all(row.fault.label() not in report.qualification_reason for row in rows)


def test_unavailable_fault_burden_cannot_be_reported_as_pass(results):
    _, rows, _ = results
    rows[1].metrics.early_alarm_burden = None
    report = report_for(results)
    assert "early alarm time is unavailable" in report.qualification_reason
    assert rows[1].fault.label() in report.qualification_reason


def test_incomplete_coverage_and_passing_result(results):
    report = report_for(results)
    assert "all 2 required faults met" in report.qualification_reason
    results[1][0].coverage_complete = False
    report = report_for(results)
    assert "did not cover all expected histories" in report.qualification_reason


def test_final_reason_uses_final_partition(results):
    bundle, rows, _ = results
    development = report_for(results)
    rows = [row.model_copy(deep=True) for row in rows]
    for row in rows:
        row.partition = Partition.holdout
    rows[1].metrics.early_alarm_burden = .25
    bundle.scenario_results.extend(rows)
    final = report_for((bundle, rows, results[2]), Partition.holdout)
    assert "25.00%" in final.qualification_reason
    assert decision(bundle, "xgboost/xgb1").qualification_reason == development.qualification_reason
    assert all("partition=holdout" in answer.link for answer in final.guide)


def test_historical_failure_keeps_source_bundle_unchanged():
    bundle = load_bundle(Path(__file__).resolve().parents[1] / "evidence" / "bundle.json")
    before = bundle.model_dump_json()
    report = decision(bundle, "logistic_regression/lr2")
    assert "41/80" in report.qualification_reason
    assert "70.0% minimum" in report.qualification_reason
    assert report.guide[0].answer.startswith(report.qualification_reason)
    assert bundle.model_dump_json() == before


def test_older_verdict_uses_recorded_burden_cases(results):
    bundle, rows, _ = results
    rows[1].metrics.early_alarm_burden = .25
    report_for(results)
    verdict = bundle.development_selection.ranked[0]
    verdict.worst_burden_required = None
    verdict.worst_burden_scenario_id = None
    reason = decision(bundle, "xgboost/xgb1").qualification_reason
    assert "25.00% early alarm time" in reason
    assert rows[1].fault.label() in reason


def test_rounded_burden_is_marked_approximate_when_over_limit(results):
    results[1][1].metrics.early_alarm_burden = .1000001
    report = report_for(results)
    assert "about 10.00% early alarm time, above the 10.0% maximum" in report.qualification_reason
