"""Meaning and availability of proposed diagnostics, not just citation membership."""
import json
from pathlib import Path

import pytest

from app.assistant.deep import collect_deep_evidence, provider_synthesis_schema
from app.assistant.investigation import EvidenceTools
from app.assistant.schemas import AnalysisRequest, DeepTest
from app.config import get_settings
from app.evidence.bundle import load_bundle


def evidence(candidates=None):
    bundle = load_bundle(get_settings().bundle_path)
    tools = EvidenceTools(bundle, AnalysisRequest(task="deep", candidates=candidates or [
        "xgboost_augmented/aug3", "logistic_regression/lr2"]))
    observations, packet, aliases, _ = collect_deep_evidence(tools)
    return tools, observations, packet, aliases


def proposal(packet, *, model="model-2", check="score_persistence"):
    id = next(row["id"] for row in packet["observations"] if row["model"] == model)
    return {"hypotheses": [{"title": "Scores or persistence may limit warnings",
        "explanation": f"{model} may lose useful score crossings under missing readings.",
        "alternative": "Alert persistence may instead prevent an active warning despite crossings.",
        "observation_ids": [id]}], "gaps": ["Aggregate undetected counts cannot distinguish late from missed histories."],
        "next_tests": [{"title": "Separate score weakness from persistence", "model": model,
            "check_type": check, "focus": "Inspect the relation between score crossings and active warning transitions.",
            "signal": {"score_persistence": "crossings_without_warning", "sensor_quality": "sensor_quality_anomaly", "threshold_sensitivity": "threshold_tradeoff"}.get(check, "preprocessing_contract_mismatch"),
            "observation_ids": [id]}]}


def compose(packet, observations, aliases, output):
    from app.assistant.diagnostic_checks import compose_checks
    model = provider_synthesis_schema([row.id for row in observations], packet=packet)
    return compose_checks(model.model_validate(output), packet, observations, aliases)[0]


def test_provider_can_abstain_without_fabricating_an_explanation():
    _, observations, packet, aliases = evidence()
    output = proposal(packet)
    output["hypotheses"] = []
    report = compose(packet, observations, aliases, output)
    assert report.hypotheses == []
    assert len(report.next_tests) == 1


def test_paid_answer_cannot_turn_a_tentative_opening_into_observed_scores():
    capture = json.loads((Path(__file__).parent / "fixtures/deep_unqualified_scores_20261011.json").read_text())
    _, observations, _, aliases = evidence()
    report = compose(capture["packet"], observations, aliases, capture["parsed"])
    assert report.hypotheses == []
    assert len(report.next_tests) == 1


def test_previous_capture_threshold_confusion_is_filtered_without_losing_check():
    capture = json.loads((Path(__file__).parent / "fixtures/deep_refined_reasoning_20261011.json").read_text())
    _, observations, _, aliases = evidence()
    report = compose(capture["packet"], observations, aliases, capture["parsed"])
    assert report.hypotheses == []  # Immutable previous answer confused warning state with scores.
    assert report.next_tests[0].model == "model-2"
    assert report.next_tests[0].check_type == "score_persistence"
    assert report.next_tests[0].readiness == "needs_evidence"
    assert any("preprocessing" in value for value in report.next_tests[0].prerequisites)


def test_explicit_focus_is_unverified_input_not_a_recorded_finding():
    bundle = load_bundle(get_settings().bundle_path)
    context = AnalysisRequest(task="deep", candidates=["logistic_regression/lr2"], investigation_focus="Which checks distinguish weak scores from persistence?")
    _, packet, _, _ = collect_deep_evidence(EvidenceTools(bundle, context))
    supplied = packet["supporting_evidence"]["engineer_context"]
    assert supplied["verified"] is False
    assert supplied["status"] == "supplied"
    assert supplied["fields"]["investigation_focus"] == context.investigation_focus


def test_model_capabilities_and_request_scoped_diagnostic_schema():
    _, observations, packet, _ = evidence()
    assert packet["diagnostic_contract"]["models"]["model-1"]["architecture"] == "trees"
    assert packet["diagnostic_contract"]["models"]["model-2"]["architecture"] == "linear"
    assert all(not row["neural_layers"] for row in packet["diagnostic_contract"]["models"].values())
    schema = provider_synthesis_schema([row.id for row in observations], packet=packet)
    value = proposal(packet)
    value["next_tests"][0]["model"] = "model-3"
    with pytest.raises(ValueError):
        schema.model_validate(value)
    value = proposal(packet)
    value["next_tests"][0]["check_type"] = "intermediate_layers"
    with pytest.raises(ValueError):
        schema.model_validate(value)
    value = proposal(packet)
    value["next_tests"][0]["procedure"] = "Uncontrolled free-form test"
    with pytest.raises(ValueError):
        schema.model_validate(value)


def test_missing_traces_are_prerequisites_not_implied_available():
    _, observations, packet, aliases = evidence()
    output = compose(packet, observations, aliases, proposal(packet))
    item = output.next_tests[0]
    assert item.readiness == "needs_evidence"
    assert item.model == "model-2"
    assert any("matched clean/faulted" in row for row in item.prerequisites)
    assert "own threshold" in item.procedure
    assert "model fixed" in " ".join(item.controls)
    assert "missing-reading flags" in item.procedure and "median imputation" in item.procedure


def test_quality_records_available_for_relevant_channel_only():
    _, observations, packet, aliases = evidence()
    result = compose(packet, observations, aliases, proposal(packet, check="sensor_quality"))
    assert result.next_tests[0].readiness == "inspect_now"
    packet["supporting_evidence"]["sensor_quality"]["items"] = []
    result = compose(packet, observations, aliases, proposal(packet, check="sensor_quality"))
    assert result.next_tests[0].readiness == "needs_evidence"


def test_threshold_check_enforces_all_controls_without_provider_word_gates():
    _, observations, packet, aliases = evidence()
    result = compose(packet, observations, aliases, proposal(packet, check="threshold_sensitivity"))
    item = result.next_tests[0]
    assert all(term in item.procedure for term in ("development", "own threshold", "early-alarm burden", "timely", "late", "missed"))
    assert "model fixed" in " ".join(item.controls)
    assert item.readiness == "needs_evidence"  # Compact summaries cannot support a sweep.


@pytest.mark.parametrize("text", [
    "Run both models with synchronized thresholds.",
    "Inspect intermediate neural layers for learned features.",
    "Compare models at identical numeric thresholds.",
    "The weakness is primarily due to threshold choice.",
    "Absent coverage indicates incomplete training.",
    "Missing coverage prevents knowing whether incomplete training explains performance.",
])
def test_relevant_citations_do_not_admit_invalid_semantics(text):
    _, observations, packet, aliases = evidence()
    output = proposal(packet)
    output["next_tests"][0]["focus"] = text
    with pytest.raises(ValueError):
        compose(packet, observations, aliases, output)


def test_check_cannot_use_other_models_patterns_or_support():
    _, observations, packet, aliases = evidence()
    output = proposal(packet)
    output["next_tests"][0]["observation_ids"] = [next(row["id"] for row in packet["observations"] if row["model"] == "model-1")]
    with pytest.raises(ValueError):
        compose(packet, observations, aliases, output)


def test_hypothesis_comparing_models_needs_citations_from_both():
    _, observations, packet, aliases = evidence()
    output = proposal(packet)
    output["hypotheses"][0]["alternative"] = "Model-1 might sustain crossings through different scoring behavior."
    with pytest.raises(ValueError):
        compose(packet, observations, aliases, output)
    output["hypotheses"][0]["observation_ids"].append(next(row["id"] for row in packet["observations"] if row["model"] == "model-1"))
    assert compose(packet, observations, aliases, output).hypotheses


def test_alias_case_and_complete_outcomes_are_checked_without_rewriting_text():
    _, observations, packet, aliases = evidence()
    output = proposal(packet)
    output["next_tests"][0]["focus"] = "Does Model-2 cross its own threshold without a warning?"
    assert compose(packet, observations, aliases, output).next_tests
    output["next_tests"][0]["signal"] = "preprocessing_contract_mismatch"
    with pytest.raises(ValueError):
        compose(packet, observations, aliases, output)
    output = proposal(packet)
    output["next_tests"][0]["focus"] = "Inspect model-1 score crossings."
    with pytest.raises(ValueError):
        compose(packet, observations, aliases, output)


def test_reserved_evidence_never_admits_sensitivity_or_new_diagnostics():
    _, observations, packet, aliases = evidence()
    packet["partition"] = "holdout"
    with pytest.raises(ValueError):
        compose(packet, observations, aliases, proposal(packet, check="threshold_sensitivity"))


def test_old_saved_test_has_unknown_availability_and_remains_readable():
    fixture = json.loads((Path(__file__).parent / "fixtures/deep_live_aug3_20261011.json").read_text())
    old = fixture["next_tests"][0].copy()
    old["interpretation"] = "Previously recorded conditional outcomes."
    old.pop("if_signal_observed")
    old.pop("if_signal_absent")
    saved = DeepTest.model_validate(old)
    assert saved.readiness is None and saved.prerequisites == []


def test_same_threshold_is_valid_for_matched_histories_of_one_model():
    from app.assistant.diagnostic_checks import semantic_text
    assert semantic_text("Inspect matched clean and faulted histories at the same threshold.")
    assert semantic_text("Never synchronize thresholds across models.")
    assert semantic_text("Does model-2 show weak or non-persistent scores causing late or missed warnings?")
    assert not semantic_text("Model-2 shows weak scores leading to missed warnings.")
    assert not semantic_text("Model-1 is robust to dropout-induced faults.")


def test_paid_invalid_layer_and_synchronized_threshold_checks_are_rejected():
    from app.assistant.diagnostic_checks import semantic_text
    captured = json.loads((Path(__file__).parent / "fixtures/deep_live_comparison_balanced-reversed_20261011.json").read_text())
    tests = captured["parsed"]["next_tests"]
    assert any(not semantic_text(item["procedure"]) for item in tests)
    assert any(not semantic_text(item["title"]) for item in tests)


def test_exact_paid_comparison_rejects_unsupported_alternative_and_robustness_claim():
    _, observations, packet, aliases = evidence()
    capture = json.loads((Path(__file__).parent / "fixtures/deep_checked_comparison_20261011.json").read_text())
    assert packet["observations"] == capture["packet"]["observations"]
    with pytest.raises(ValueError):
        compose(packet, observations, aliases, capture["parsed"])


def test_same_provider_output_cannot_change_the_trained_feature_contract():
    _, observations, packet, aliases = evidence()
    output = proposal(packet)
    output["next_tests"][0]["focus"] = "Warnings recover when missingness is represented explicitly."
    with pytest.raises(ValueError):
        compose(packet, observations, aliases, output)


def test_observable_discriminator_owns_branches_and_rejects_provider_inversion():
    _, observations, packet, aliases = evidence()
    output = proposal(packet, check="preprocessing_audit")
    item = compose(packet, observations, aliases, output).next_tests[0]
    assert "differs from its declared feature contract" in item.expected_signal
    assert "If observed: Investigate that mismatch" in item.interpretation
    assert "If absent: A consistent contract does not establish adequate fault handling" in item.interpretation
    output["next_tests"][0]["if_signal_absent"] = "Missing records establish a threshold problem."
    with pytest.raises(ValueError):
        compose(packet, observations, aliases, output)


def test_actual_paid_signal_question_survives_without_inventing_explanations():
    _, observations, packet, aliases = evidence()
    capture = json.loads((Path(__file__).parent / "fixtures/deep_checked_signals_20261011.json").read_text())
    assert packet["observations"] == capture["packet"]["observations"]
    output = compose(packet, observations, aliases, capture["parsed"])
    assert output.hypotheses == []
    assert len(output.next_tests) == 1
    item = output.next_tests[0]
    assert item.check_type == "score_persistence" and item.model == "model-2"
    assert item.readiness == "needs_evidence" and len(item.prerequisites) == 2
    assert "scores remain below" in item.expected_signal.lower()
    assert "shift attention to sustained crossings" in item.interpretation
    assert item.title == "Inspect score response and warning persistence · model-2"
    assert "caused by" not in item.title and " in Y" not in item.title


def test_original_sensor_quality_cannot_rule_out_injected_fault_response():
    from app.assistant.diagnostic_checks import semantic_text
    assert not semantic_text("Verify that sensor signal quality shows no anomalies that could explain detection failure.")
    assert semantic_text("Inspect recorded missingness and flat readings in the original dataset profile.")


def test_quality_controls_keep_mixed_profile_descriptive_and_no_hypothesis_report_exports():
    from app.assistant.evidence import with_brief
    from app.assistant.schemas import DeepReport
    tools, observations, packet, aliases = evidence()
    item = compose(packet, observations, aliases, proposal(packet, check="sensor_quality")).next_tests[0]
    assert "may include reserved equipment" in item.controls[0]
    capture = json.loads((Path(__file__).parent / "fixtures/deep_checked_signals_20261011.json").read_text())
    checked = compose(packet, observations, aliases, capture["parsed"])
    report = DeepReport(**checked.model_dump(), observations=observations, inspected_cases=packet["inspected_cases"],
        pattern_count=packet["total_patterns"], latency_seconds=0, limitations=["No AI explanation passed verification."])
    result = tools.result.model_copy(update={"deep_report": report})
    brief = with_brief(result, tools.context.model_copy(update={"task": "brief"}))
    assert "Collect evidence first" in brief.brief_draft
    assert all(value in brief.brief_draft for value in report.next_tests[0].prerequisites)
    assert len(brief.brief_draft) <= 12000


@pytest.mark.parametrize("candidates", [
    ["xgboost_augmented/aug3", "logistic_regression/lr2"],
    ["logistic_regression/lr2", "xgboost_augmented/aug3"],
])
def test_regular_comparison_prioritizes_failed_model_independent_of_order(candidates):
    tools, _, _, _ = evidence(candidates)
    context = tools.context.model_copy(update={"task": "compare"})
    result = EvidenceTools(tools.bundle, context).local()
    assert result.actions and "logistic_regression%2Flr2" in result.actions[0].href


@pytest.mark.parametrize("text", [
    "Warnings might remain below its own threshold.",
    "Warnings could instead cross the threshold briefly.",
    "Warnings are above the threshold.",
])
def test_warning_state_cannot_be_described_as_a_threshold_score(text):
    from app.assistant.diagnostic_checks import semantic_text
    assert not semantic_text(text)


@pytest.mark.parametrize("text", [
    "Model scores may remain below their own threshold while warnings are inactive.",
    "Does model-2 produce sustained above-threshold scores that fail to trigger warnings, or do scores remain below threshold?",
    "Warning scores may remain below the threshold.",
])
def test_score_threshold_wording_is_not_rejected_for_mentioning_warnings(text):
    from app.assistant.diagnostic_checks import semantic_text
    assert semantic_text(text)
