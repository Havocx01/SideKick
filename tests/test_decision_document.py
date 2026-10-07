from pathlib import Path

import pytest

from app.evidence.bundle import load_bundle
from app.experiments.export import render_report
from app.schemas import Partition


@pytest.fixture
def bundle():
    return load_bundle(Path(__file__).resolve().parents[1] / "evidence" / "bundle.json")


def test_report_separates_inspected_failure_from_recommendation(bundle):
    before = bundle.model_dump_json()
    html, source = render_report(bundle, "logistic_regression/lr2")
    assert "Revise before further evaluation" in html
    assert "Logistic regression (lr2) does not meet" in html
    assert "Recommended configuration" in html
    assert "Augmented XGBoost (aug3)" in html
    assert "Engineering disposition" in html and "Required fault evidence" in html
    assert "41 / 80" in html and "24" in html and "15" in html
    assert "not deployment approval" in html
    assert "Engineer sign-off" in html and "Not recorded" in html
    assert source["report_candidate"] == "logistic_regression/lr2"
    assert bundle.model_dump_json() == before


@pytest.mark.parametrize("stored_identifier", [False, True])
def test_report_keeps_detection_and_burden_cases_distinct(bundle, stored_identifier):
    focus = bundle.development_selection.recommended
    cases = [row for row in bundle.scenario_results if row.required and row.candidate == focus.candidate and row.config_id == focus.config_id]
    highest = max(cases, key=lambda row: row.metrics.early_alarm_burden)
    assert focus.worst_scenario_id != highest.scenario_id
    if stored_identifier:
        for item in [focus, *bundle.development_selection.ranked]:
            if item.candidate == focus.candidate and item.config_id == focus.config_id:
                item.worst_burden_scenario_id = highest.scenario_id
    html, _ = render_report(bundle)
    assert "Lowest detection case" in html and "Highest early alarm case" in html
    assert focus.worst_scenario_id in html and highest.scenario_id in html
    assert "Fresh validation required" in html
    assert "Previously examined" in html
    assert "Alert threshold" in html


def test_final_report_uses_final_criteria_and_does_not_mix_required_cases(bundle):
    bundle.final_evaluation = bundle.development_selection.model_copy(deep=True)
    bundle.final_evaluation.partition = Partition.holdout
    bundle.final_evaluation.criteria.min_detection_fraction = .98
    bundle.final_evaluation.criteria.max_early_alarm_burden = .02
    html, source = render_report(bundle, partition=Partition.holdout)
    assert "Minimum in-time warnings</dt><dd>98.0%" in html
    assert "Maximum early alarm time</dt><dd>2.0%" in html
    assert "No scenario-level evidence is stored for this model and partition." in html
    assert source["report_partition"] == "holdout"
    assert "Site review required" in html


def test_report_escapes_source_text_and_preserves_missing_measurements(bundle):
    bundle.profile.source = "<script>alert('data')</script>"
    focus = bundle.development_selection.ranked[0]
    focus.clean.early_alarm_burden = None
    html, _ = render_report(bundle, f"{focus.candidate.value}/{focus.config_id}")
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html
    assert "Unavailable" in html
    assert 'class="print-button"' in html and "@media print" in html


@pytest.mark.parametrize("empty", [False, True])
def test_report_never_invents_a_recommendation_or_metrics(bundle, empty):
    bundle.development_selection.recommended = None
    for item in bundle.development_selection.ranked:
        item.qualifies = False
    if empty:
        bundle.development_selection.ranked = []
    html, _ = render_report(bundle)
    assert "None. No configuration qualifies in this partition." in html
    assert "Revise before further evaluation" in html
    if empty:
        assert "No candidate metrics are available." in html
        assert 'class="key-results"' not in html
