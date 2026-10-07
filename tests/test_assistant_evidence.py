from pathlib import Path

import pytest

from app.assistant.evidence import build_analysis
from app.assistant.schemas import AnalysisRequest
from app.evidence.bundle import load_bundle
from app.schemas import Partition


@pytest.fixture
def bundle():
    return load_bundle(Path(__file__).resolve().parents[1] / "evidence" / "bundle.json")


def request(bundle, task="investigate", **kwargs):
    v = bundle.development_selection.ranked[0]
    return AnalysisRequest(task=task, experiment_id=bundle.experiment_id,
                           candidates=kwargs.pop("candidates", [f"{v.candidate.value}/{v.config_id}"]), **kwargs)


def test_scoped_reproducible_evidence(bundle):
    context = request(bundle)
    result = build_analysis(bundle, context)
    assert result.evidence_digest == build_analysis(bundle, context).evidence_digest
    assert {s.candidate for s in result.sources} == set(context.candidates)
    assert all(s.href.startswith("/comparison?") for s in result.sources)
    assert all(s.unit and s.metric for s in result.sources)
    bundle.development_selection.ranked[0].required_passed -= 1
    assert result.evidence_digest != build_analysis(bundle, context).evidence_digest


def test_wrong_configuration_experiment_and_unavailable_partition(bundle):
    for context in [request(bundle, candidates=["xgboost/nonexistent"]), request(bundle).model_copy(update={"experiment_id": "other"})]:
        with pytest.raises(ValueError):
            build_analysis(bundle, context)
    bundle.final_evaluation = None
    with pytest.raises(ValueError):
        build_analysis(bundle, request(bundle, partition=Partition.holdout))


def test_detection_and_burden_remain_separate(bundle):
    context = request(bundle)
    verdict = bundle.development_selection.ranked[0]
    verdict.clean.early_alarm_burden = .9
    rows = [r for r in bundle.scenario_results if f"{r.candidate.value}/{r.config_id}" == context.candidates[0] and r.partition == context.partition and r.required and r.fault]
    rows[0].metrics.detection_fraction = .1
    rows[1].metrics.early_alarm_burden = .8
    result = build_analysis(bundle, context)
    assert any(s.metric == "early_alarm_burden" and s.scenario_id == "clean" and s.value == "0.9" for s in result.sources)
    assert any(s.metric == "detection_fraction" and s.scenario_id == rows[0].scenario_id and s.value == "0.1" for s in result.sources)
    assert any(s.metric == "early_alarm_burden" and s.scenario_id == rows[1].scenario_id and s.value == "0.8" for s in result.sources)


def test_lowest_detection_and_highest_burden_are_separate_cases(bundle):
    context = request(bundle)
    rows = [r for r in bundle.scenario_results if f"{r.candidate.value}/{r.config_id}" == context.candidates[0] and r.partition == context.partition and r.required and r.fault]
    rows[0].metrics.detection_fraction = .05
    rows[1].metrics.early_alarm_burden = .95
    result = build_analysis(bundle, context)
    titles = {f.title: f for f in result.findings}
    assert rows[0].fault.label() in titles["Lowest fault detection"].detail
    assert rows[1].fault.label() in titles["Highest early alarm time"].detail
    rows[0].metrics.early_alarm_burden = .99
    combined = {f.title for f in build_analysis(bundle, context).findings}
    assert "Weakest fault case" in combined and "Highest early alarm time" not in combined


def test_sources_are_displayed_with_context_and_deep_links(bundle):
    result = build_analysis(bundle, request(bundle))
    qualification = next(s for s in result.sources if s.metric == "qualifies")
    assert qualification.display in {"Yes", "No"} and "Development" in qualification.context
    fault = next(s for s in result.sources if s.scenario_id not in (None, "clean"))
    assert fault.href.endswith("#fault-results")
    assert fault.display.endswith("%") or fault.display == "Unavailable"
    assert any(a.href.endswith("#fault-results") for a in result.actions)


def test_missing_metrics_and_brief(bundle):
    bundle.development_selection.ranked[0].clean.early_alarm_burden = None
    result = build_analysis(bundle, request(bundle, "brief"))
    assert any("unavailable" in f.detail for f in result.findings)
    assert any("Engineer review draft" in text for text in result.limitations)
    draft = result.brief_draft
    assert draft.startswith("Engineer review draft")
    for heading in ["Findings", "Evidence", "Proposed next checks", "Limitations"]:
        assert f"\n{heading}\n" in draft
    assert build_analysis(bundle, request(bundle)).brief_draft is None


def test_comparison_is_descriptive(bundle):
    keys = [f"{v.candidate.value}/{v.config_id}" for v in bundle.development_selection.ranked[:2]]
    bundle.paired_comparisons = []
    result = build_analysis(bundle, request(bundle, "compare", candidates=keys))
    assert any("Second minus first" in f.detail for f in result.findings)
    assert any("does not isolate" in text for text in result.limitations)
    assert {s.candidate for s in result.sources} == set(keys)
    assert result.findings[0].title == "Comparison overview" and "Independently selected" in result.findings[0].detail
    assert any("recommendation is unchanged" in text or "No model met" in text for text in result.limitations)
    for metric in ["qualifies", "required_passed", "clean_detection", "clean_early_alarm_burden"]:
        assert {s.candidate for s in result.sources if s.metric == metric} == set(keys)


def test_warning_uses_stored_alert_not_threshold(bundle):
    series = next(s for s in bundle.replay_series if s.partition == Partition.out_of_fold)
    point = series.points[0]
    point.score = 1
    point.alert = False
    context = request(bundle, "warning", candidates=[f"{series.candidate.value}/{series.config_id}"],
                      scenario_id=series.scenario_id, equipment_id=series.equipment_id, cycle=point.cycle)
    result = build_analysis(bundle, context)
    assert "inactive" in result.findings[0].detail
    assert any(s.metric == "alert_active" and s.value == "False" for s in result.sources)
    assert any(f"cycle={point.cycle}" in a.href for a in result.actions)
    unrecorded = build_analysis(bundle, context.model_copy(update={"cycle": 999999}))
    assert unrecorded.findings[0].title == "Cycle not recorded"
    assert not any(s.metric == "alert_active" for s in unrecorded.sources)
    assert any(f.title == "History outcome" for f in unrecorded.findings)
    missing = build_analysis(bundle, context.model_copy(update={"equipment_id": "missing"}))
    assert missing.findings[0].title == "Replay unavailable"
    assert any(f.title in {"Meets test limits", "Does not meet test limits"} for f in missing.findings)
    assert not any(a.id == "replay" for a in missing.actions)


def test_unmatched_explanation_not_reused(bundle):
    from app.schemas import AlertExplanation, ShapContribution
    series = next(s for s in bundle.replay_series if s.partition == Partition.out_of_fold and s.fault is None)
    context = request(bundle, "warning", candidates=[f"{series.candidate.value}/{series.config_id}"],
                      scenario_id=series.scenario_id, equipment_id=series.equipment_id, cycle=series.points[0].cycle)
    explanation = AlertExplanation(equipment_id=series.equipment_id, cycle=context.cycle,
                                   candidate="wrong/model", score=.5,
                                   contributions=[ShapContribution(feature="sensor", value=500, contribution=.2)])
    bundle.explanations = [explanation]
    assert not any(s.metric == "feature_contribution" for s in build_analysis(bundle, context).sources)
    explanation.candidate = context.candidates[0]
    assert any(s.metric == "feature_contribution" for s in build_analysis(bundle, context).sources)
    explanation.cycle += 1
    assert not any(s.metric == "feature_contribution" for s in build_analysis(bundle, context).sources)
