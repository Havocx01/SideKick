"""The copilot's tools and its numeric-claim guard."""

from __future__ import annotations

import pytest

from app.copilot.fallback import answer_without_llm
from app.copilot.tools import ToolError
from app.copilot.verify import collect_values, unverified, verify_answer

EXPECTED_TOOLS = {
    "profile_dataset",
    "map_columns",
    "train_candidates",
    "run_fault_tests",
    "query_runs",
    "draft_report",
}


class TestRegistry:
    def test_exactly_the_six_documented_tools_are_exposed(self, registry):
        assert set(registry.names()) == EXPECTED_TOOLS

    def test_every_schema_is_a_closed_object(self, registry):
        for schema in registry.schemas():
            parameters = schema["function"]["parameters"]
            assert parameters["type"] == "object"
            # Closed schemas mean an unexpected argument is rejected, not ignored.
            assert parameters.get("additionalProperties") is False
            assert schema["function"]["description"]

    def test_an_unknown_tool_is_refused(self, registry):
        with pytest.raises(ToolError, match="unknown tool"):
            registry.call("delete_everything", {})

    def test_no_tool_returns_a_prediction(self, registry):
        """The copilot must not be able to obtain a score for a cycle."""
        for name in registry.names():
            payload = registry.call(name, {})
            flattened = str(payload).lower()
            assert "predict_proba" not in flattened
            assert "raw_readings" not in flattened


class TestTools:
    def test_profile_reports_the_recorded_hash(self, registry, bundle):
        payload = registry.call("profile_dataset", {})
        assert payload["data_hash"] == bundle.profile.data_hash
        assert payload["equipment_count"] == bundle.profile.equipment_count

    def test_training_is_described_but_never_started(self, registry):
        payload = registry.call("train_candidates", {"min_detection_fraction": 0.8})
        assert payload["started"] is False
        assert "scripts/run_pipeline.py" in payload["command"]
        assert payload["config_fingerprint"]

    def test_fault_tests_name_the_worst_case(self, registry):
        payload = registry.call("run_fault_tests", {"required_only": True})
        assert payload["scenarios"] > 0
        for entry in payload["per_candidate"].values():
            assert entry["worst_scenario_id"]
            assert entry["worst_detection_fraction"] <= entry["mean_detection_fraction"] + 1e-9

    def test_querying_a_nonexistent_scenario_explains_itself(self, registry):
        payload = registry.call("query_runs", {"scenario_id": "not-a-scenario"})
        assert payload["results"] == []
        assert "identifiers look like" in payload["note"]

    def test_an_unknown_metric_is_refused_with_the_available_names(self, registry):
        with pytest.raises(ToolError, match="unknown metric"):
            registry.call("query_runs", {"metric": "accuracy"})

    def test_the_report_carries_the_criteria_and_the_limitations(self, registry):
        payload = registry.call("draft_report", {})
        assert payload["criteria"]["min_detection_fraction"] > 0
        assert payload["limitations"]
        assert payload["outcome"] in {"qualified", "none_qualified"}

    def test_the_report_states_whether_the_holdout_was_scored(self, registry):
        assert registry.call("draft_report", {})["final_evaluation_run"] is False


class TestVerification:
    def test_a_figure_returned_by_a_tool_is_accepted(self):
        claims = verify_answer("Detection was 93%.", [{"detection_fraction": 0.93}])
        assert not unverified(claims)

    def test_a_fabricated_figure_is_caught(self):
        claims = verify_answer("Detection was 88%.", [{"detection_fraction": 0.93}])
        assert [claim.text for claim in unverified(claims)] == ["88%"]

    def test_both_the_decimal_and_the_percentage_form_are_accepted(self):
        payload = [{"burden": 0.042}]
        assert not unverified(verify_answer("The burden was 0.042.", payload))
        assert not unverified(verify_answer("The burden was 4.2%.", payload))

    def test_small_counts_in_ordinary_prose_are_not_treated_as_claims(self):
        claims = verify_answer("We compared 4 candidates across 3 fault types.", [])
        assert not unverified(claims)

    def test_a_list_length_is_a_legitimate_claim(self):
        payload = [{"sensors_tested": ["a"] * 16}]
        assert not unverified(verify_answer("16 sensors were tested.", payload))

    def test_nested_values_are_reachable(self):
        values = collect_values({"outer": [{"inner": {"detection": 0.77}}]})
        assert 0.77 in values
        assert 77.0 in values

    def test_booleans_are_not_mistaken_for_numbers(self):
        assert collect_values({"qualifies": True}) == set()

    def test_an_answer_with_an_unmatched_figure_is_annotated(self, registry):
        from app.copilot.verify import annotate

        claims = verify_answer("Detection was 88%.", [{"detection_fraction": 0.93}])
        annotated = annotate("Detection was 88%.", claims)
        assert "Unverified figures" in annotated
        assert "88%" in annotated


class TestFallback:
    def test_a_recommendation_question_is_answered_from_evidence(self, registry):
        answer = answer_without_llm("Which model should we deploy?", registry, reason="no key")
        assert answer.degraded
        assert answer.unverified_claims == 0
        assert "Criteria set before selection" in answer.text

    def test_a_robustness_question_names_the_worst_case(self, registry):
        answer = answer_without_llm(
            "How did the models hold up under sensor faults?", registry, reason="no key"
        )
        assert "Fault tests" in answer.text
        assert "age baseline" in answer.text

    def test_a_data_question_returns_the_profile(self, registry):
        answer = answer_without_llm("Is anything wrong with the data?", registry, reason="no key")
        assert "readings across" in answer.text

    def test_a_metric_question_separates_late_from_missed(self, registry):
        answer = answer_without_llm("Show the detection rates.", registry, reason="no key")
        assert "Late" in answer.text and "Missed" in answer.text
        assert "counted separately" in answer.text

    def test_every_fallback_answer_states_why_it_is_degraded(self, registry):
        for question in [
            "Which model?",
            "How robust?",
            "What is the data like?",
            "Detection rates?",
        ]:
            answer = answer_without_llm(question, registry, reason="no API key is configured")
            assert "no API key is configured" in answer.text
            assert answer.degraded

    def test_no_fallback_answer_contains_an_unverified_figure(self, registry):
        for question in ["Which model?", "How robust?", "Data quality?", "Detection?"]:
            answer = answer_without_llm(question, registry, reason="test")
            assert answer.unverified_claims == 0, f"{question}: {answer.claims}"
