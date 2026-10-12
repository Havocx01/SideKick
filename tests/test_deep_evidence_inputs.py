"""Recorded support for deep reports. No models, training or provider network."""
import json
import hashlib
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.assistant.investigation import EvidenceTools
from app.assistant.schemas import AnalysisRequest
from app.schemas import AlertExplanation, EngineOutcome, ReplayPoint, ReplaySeries, ShapContribution
from test_deep_investigation import BODY as BASE_BODY, HEADERS, completed, deep_app as deep_app, fake_provider

BODY = {**BASE_BODY, "candidates": ["logistic_regression/lr2"]}


def enriched(bundle):
    result = bundle.model_copy(deep=True)
    row = min((row for row in result.scenario_results if row.config_id == "lr2" and row.required and row.fault.kind.value == "dropout"),
              key=lambda row: row.metrics.detection_fraction)
    sensor = row.fault.sensor
    equipment = result.splits.folds[0][0]
    points = [ReplayPoint(cycle=100-rul, rul=rul, score=row.threshold + margin, alert=alert,
                          sensor_clean=987654321, sensor_faulted=123456789)
              for rul, margin, alert in [(30, .1, False), (29, -.2, False), (28, .2, False), (10, -.2, False), (9, .2, False), (8, .2, True)]]
    faulted = ReplaySeries(equipment_id=equipment, candidate=row.candidate, config_id=row.config_id,
        scenario_id=row.scenario_id, threshold=row.threshold, fault=row.fault, points=points, episodes=[],
        outcome=EngineOutcome(equipment_id=equipment, detected=False, late=True, missed=False, episode_count=1), failure_cycle=100)
    clean = faulted.model_copy(deep=True, update={"scenario_id": "clean", "fault": None,
        "outcome": EngineOutcome(equipment_id=equipment, detected=True, late=False, missed=False, episode_count=1)})
    clean.points[1].alert = True
    result.replay_series = [clean, faulted]
    result.explanations = [AlertExplanation(equipment_id=equipment, candidate="logistic_regression/lr2", cycle=71,
        score=clean.points[1].score, base_value=-.2, contributions=[ShapContribution(feature=f"{sensor}__value", value=123456789, contribution=.3)])]
    return result


def packet_for(bundle, **extra):
    from app.assistant.deep import collect_deep_evidence
    return collect_deep_evidence(EvidenceTools(bundle, AnalysisRequest.model_validate({**BODY, **extra})))


def test_support_contains_paired_warning_scores_quality_and_clean_contributions(deep_app):
    _, original = deep_app
    bundle = enriched(original)
    before = bundle.model_dump_json()
    observations, packet, aliases, priorities = packet_for(bundle)
    support = packet["supporting_evidence"]
    pair = support["paired_histories"]["items"][0]
    assert pair["clean"]["outcome"] == "timely" and pair["faulted"]["outcome"] == "late"
    assert pair["change"] == "warning_became_late"
    assert pair["threshold"] == bundle.replay_series[1].threshold
    assert pair["faulted"]["useful_window"]["above_threshold_without_active_warning"] == 2
    assert pair["fold"] == "fold-1"
    assert support["preprocessing"]["status"] == "unavailable"
    assert support["sensor_quality"]["items"]
    assert support["feature_contributions"]["items"][0]["scope"] == "clean_prediction_only"
    assert "value" not in support["feature_contributions"]["items"][0]["contributions"][0]
    assert support["equipment_and_folds"]["scope"] == "stored_replay_subset_only"
    assert pair["observation_id"] in priorities and pair["history"] in aliases
    assert any(row.kind == "supporting" and row.source_ids for row in observations)
    quality_display = next(row.text for row in observations if row.id.startswith("sensor-quality-"))
    assert "Missing readings:" in quality_display and "readings vary: yes" in quality_display
    assert "True" not in quality_display and "False" not in quality_display
    quality_record = support["sensor_quality"]["items"][0]
    assert quality_record["std"] == bundle.profile.sensors[next(
        index for index, sensor in enumerate(bundle.profile.sensors) if sensor.name == aliases[quality_record["channel"]])].std
    serialized = json.dumps(packet)
    assert "987654321" not in serialized and "123456789" not in serialized
    assert '"equipment_id"' not in serialized and '"sensor_clean"' not in serialized  # IDs/readings stay local.
    assert bundle.model_dump_json() == before


@pytest.mark.parametrize("mismatch", ["threshold", "partition", "cycle"])
def test_unmatched_history_is_not_a_clean_fault_comparison(deep_app, mismatch):
    _, original = deep_app
    bundle = enriched(original)
    if mismatch == "threshold":
        bundle.replay_series[0].threshold = .9
    elif mismatch == "partition":
        bundle.replay_series[0].partition = "holdout"
    else:
        bundle.replay_series[0].points[0].cycle += 1
    _, packet, _, _ = packet_for(bundle)
    assert packet["supporting_evidence"]["paired_histories"]["items"] == []


def test_optional_context_is_bounded_trimmed_and_not_automatically_copied(deep_app):
    from app.assistant.schemas import DeepEngineerContext
    _, bundle = deep_app
    _, empty, _, _ = packet_for(bundle)
    assert empty["supporting_evidence"]["engineer_context"]["status"] == "not_supplied"
    context = DeepEngineerContext(equipment_type="  Cooling pump  ", sensor_meaning="Bearing temperature", decision="Review missing warnings")
    assert context.equipment_type == "Cooling pump"
    _, packet, _, _ = packet_for(bundle, engineer_context=context.model_dump())
    assert packet["supporting_evidence"]["engineer_context"]["verified"] is False
    assert packet["supporting_evidence"]["engineer_context"]["fields"]["decision"] == context.decision
    with pytest.raises(ValueError):
        DeepEngineerContext(decision="x" * 2001)
    with pytest.raises(ValueError):
        AnalysisRequest.model_validate({**BODY, "task": "investigate", "engineer_context": context.model_dump()})


def test_support_changes_context_currency_without_paying_or_altering_evidence(deep_app):
    app, original = deep_app
    context = AnalysisRequest.model_validate(BODY)
    old = app.state.assistant.identities(original, context, True)
    new = app.state.assistant.identities(enriched(original), context, True)
    assert old[0] != new[0] and old[1] != new[1]


def test_support_citations_and_context_survive_api_and_brief(deep_app, monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import routes_assistant
    app, original = deep_app
    monkeypatch.setattr(routes_assistant, "bundle", lambda *_: enriched(original))
    app.state.assistant.store.set_workspace_consent(True)
    def cite_support(output):
        output["hypotheses"][0]["observation_ids"] = ["pattern-1", "history-summary-1"]
        output["next_tests"][0]["observation_ids"] = ["pattern-1", "history-summary-1"]
        output["next_tests"][0]["procedure"] = "Compare the recorded scores with active warnings while keeping the model fixed."
    calls = fake_provider(monkeypatch, cite_support)
    with TestClient(app) as client:
        start = client.post("/api/assistant/analyses", json={**BODY, "engineer_context": {"equipment_type": "Pump"}}, headers=HEADERS).json()
        record = completed(client, start["id"])
        assert record["result"]["mode"] == "ai", record["result"]["fallback_reason"]
        assert "missing-reading flags" in record["result"]["deep_report"]["next_tests"][0]["procedure"]
        assert "median imputation" in record["result"]["deep_report"]["next_tests"][0]["procedure"]
        brief = client.post(f"/api/assistant/analyses/{record['id']}/review", headers=HEADERS).json()
        assert brief["context"]["engineer_context"]["equipment_type"] == "Pump"
        assert brief["result"]["deep_report"] == record["result"]["deep_report"]
    assert len(calls) == 1


def test_new_evaluations_capture_actual_preprocessing_and_fold_outcomes_without_execution(deep_app):
    import numpy as np
    from sklearn.preprocessing import StandardScaler
    from app.config import EXPERIMENT
    from app.features.build import FeatureBuilder, Preprocessor
    from app.evidence.diagnostics import recorded_diagnostics
    _, original = deep_app
    bundle = enriched(original)
    preprocessor = Preprocessor(("channel",), np.array([2.]), np.array([1.]))
    builder = FeatureBuilder(preprocessor, replace(EXPERIMENT, feature_window=7))
    candidate = SimpleNamespace(uses_sensors=True, _pipeline=SimpleNamespace(named_steps={"scale": StandardScaler()}))
    folds = [SimpleNamespace(builder=builder, preprocessor=preprocessor, candidates={BODY["candidates"][0]: candidate})
             for _ in bundle.splits.folds]
    replay = bundle.replay_series[1]
    result = SimpleNamespace(training=SimpleNamespace(folds=folds, splits=bundle.splits, specs={BODY["candidates"][0]: candidate}),
        matrix=SimpleNamespace(equipment_metrics={(BODY["candidates"][0], replay.scenario_id): [SimpleNamespace(outcome=replay.outcome)]}))
    preprocessing, summaries = recorded_diagnostics(result)
    assert preprocessing.feature_window == 7
    assert preprocessing.scaling[BODY["candidates"][0]] == "standard_scaler"
    assert preprocessing.missingness == "trailing_missing_fraction"
    assert preprocessing.imputation == "training_median_before_windowing"
    assert preprocessing.fitting_scope == "training_equipment_only_in_each_development_fold"
    assert summaries[0].fold == 1 and summaries[0].late == 1 and summaries[0].detected == 0
    bundle.preprocessing, bundle.fold_fault_summaries = preprocessing, summaries
    _, packet, _, _ = packet_for(bundle)
    support = packet["supporting_evidence"]
    assert support["preprocessing"]["items"][0]["feature_window"] == 7
    assert support["equipment_and_folds"]["items"][0]["folds"][0]["late"] == 1
    bundle.preprocessing.partition = "holdout"
    bundle.fold_fault_summaries[0].partition = "holdout"
    _, packet, _, _ = packet_for(bundle)
    assert packet["supporting_evidence"]["preprocessing"]["status"] == "unavailable"
    assert packet["supporting_evidence"]["equipment_and_folds"]["status"] == "unavailable"


@pytest.mark.parametrize("mismatch", ["score", "partition", "cycle"])
def test_unmatched_contributions_are_not_used(deep_app, mismatch):
    _, bundle = deep_app
    bundle = enriched(bundle)
    explanation = bundle.explanations[0]
    if mismatch == "score":
        explanation.score += .1
    elif mismatch == "partition":
        explanation.partition = "holdout"
    else:
        explanation.cycle += 1
    _, packet, _, _ = packet_for(bundle)
    assert packet["supporting_evidence"]["feature_contributions"]["status"] == "unavailable"


def test_score_streaks_do_not_bridge_missing_scores_or_gaps(deep_app):
    from app.assistant.deep_support import _warning_summary
    _, original = deep_app
    bundle = enriched(original)
    series = bundle.replay_series[1]
    series.points = [ReplayPoint(cycle=cycle, rul=100-cycle, score=score, alert=False)
                     for cycle, score in [(70, 1.), (71, float("nan")), (72, 1.), (80, 1.)]]
    series.threshold = .5
    summary = _warning_summary(series, bundle.development_selection.criteria)
    assert summary["useful_window"]["maximum_above_threshold_streak"] == 1
    assert summary["useful_window"]["valid_scores"] == 3


def test_legacy_deep_report_reuses_historically_without_paid_regeneration(deep_app, monkeypatch):
    from fastapi.testclient import TestClient
    from app.assistant.evidence import build_analysis
    app, original = deep_app
    app.state.assistant.store.set_workspace_consent(True)
    calls = fake_provider(monkeypatch)
    with TestClient(app) as client:
        start = client.post("/api/assistant/analyses", json=BODY, headers=HEADERS).json()
        record = completed(client, start["id"])
        stored = app.state.assistant.store.get(record["id"], "owner")
        context = AnalysisRequest.model_validate(BODY)
        legacy_identity = {"evidence": build_analysis(original, context).evidence_digest,
                           "context": context.model_dump(mode="json", exclude={"engineer_context", "investigation_focus"})}
        stored.draft_fingerprint = hashlib.sha256(json.dumps(legacy_identity, sort_keys=True).encode()).hexdigest()
        stored.cache_fingerprint = "previous-contract"
        app.state.assistant.store.save(stored, "owner")
        reopened = client.post("/api/assistant/analyses?reuse=true", json=BODY, headers=HEADERS).json()
        assert reopened["id"] == stored.id and reopened["reused"]
        detail = client.get(f"/api/assistant/analyses/{stored.id}").json()
        assert detail["output_currency"] == "historical"
        brief = client.post("/api/assistant/analyses?reuse=true", json={**BODY, "task": "brief"}, headers=HEADERS).json()
        assert brief["id"] == stored.id and brief["result"]["deep_report"]
    assert len(calls) == 1


def test_changed_engineer_context_has_distinct_identity_empty_is_compatible(deep_app):
    app, bundle = deep_app
    context = AnalysisRequest.model_validate(BODY)
    empty = AnalysisRequest.model_validate({**BODY, "engineer_context": {"equipment_type": "  "}})
    entered = AnalysisRequest.model_validate({**BODY, "engineer_context": {"decision": "Review missed warnings"}})
    assert empty.engineer_context is None
    assert app.state.assistant.identities(bundle, context, True) == app.state.assistant.identities(bundle, empty, True)
    assert app.state.assistant.identities(bundle, context, True) != app.state.assistant.identities(bundle, entered, True)


def test_changed_trace_contract_marks_saved_output_historical_without_regeneration(deep_app, monkeypatch):
    from pathlib import Path
    from fastapi.testclient import TestClient
    app, _ = deep_app
    app.state.assistant.store.set_workspace_consent(True)
    calls = fake_provider(monkeypatch)
    original_read = Path.read_bytes
    with TestClient(app) as client:
        record = client.post('/api/assistant/analyses', headers=HEADERS, json=BODY).json()
        completed(client, record['id'])
        path = '/api/assistant/analyses/' + record['id']
        assert client.get(path).json()['output_currency'] == 'current'
        def changed_contract(source):
            data = original_read(source)
            return data + b'\n# revised trace admission contract\n' if source.name == 'trace_reasoning.py' else data
        monkeypatch.setattr(Path, 'read_bytes', changed_contract)
        assert client.get(path).json()['output_currency'] == 'historical'
        assert client.post('/api/assistant/analyses?reuse=true', headers=HEADERS, json=BODY).json()['id'] == record['id']
    assert len(calls) == 1


def test_support_budget_and_missing_sensor_values_are_explicit(deep_app):
    from app.assistant.deep_support import MAX_SUPPORT_BYTES
    from app.assistant.deep import MAX_INPUT_BYTES
    _, original = deep_app
    bundle = enriched(original)
    for sensor in bundle.profile.sensors:
        sensor.mean, sensor.minimum, sensor.std = None, float("nan"), float("inf")
    _, packet, _, _ = packet_for(bundle, engineer_context={"sensor_meaning": "x" * 500, "decision": "y" * 500})
    support = packet["supporting_evidence"]
    assert support["sensor_quality"]["items"][0]["mean"] is None
    assert support["sensor_quality"]["items"][0]["minimum"] is None
    assert support["sensor_quality"]["items"][0]["std"] is None
    assert len(json.dumps(support, ensure_ascii=False).encode()) <= MAX_SUPPORT_BYTES
    assert len(json.dumps(packet, separators=(",", ":")).encode()) <= MAX_INPUT_BYTES
