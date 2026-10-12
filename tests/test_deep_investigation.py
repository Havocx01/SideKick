"""Offline evidence, synthesis and paid-admission boundaries for the new report."""
import asyncio
import io
import html
import json
import zipfile
from types import SimpleNamespace
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes_assistant
from app.assistant.schemas import AnalysisRequest
from app.assistant.service import AssistantService
from app.config import get_settings
from app.evidence.bundle import load_bundle


@pytest.fixture
def deep_app(local_settings, monkeypatch):
    settings = SimpleNamespace(artifacts_dir=local_settings, mode="full", assistant_enabled=True,
        assistant_live_enabled=True, openai_api_key="mock-only", assistant_model="fixture",
        assistant_presenter_code="presenter", assistant_timeout_seconds=2,
        assistant_tasks=("investigate", "compare", "warning", "brief", "data", "deep"))
    loaded = load_bundle(get_settings().bundle_path)
    app = FastAPI()
    app.state.assistant = AssistantService(settings)
    app.include_router(routes_assistant.router)
    monkeypatch.setattr(routes_assistant, "bundle", lambda *_: loaded)
    monkeypatch.setattr(routes_assistant, "upload_context", lambda *_: False)
    monkeypatch.setattr(routes_assistant, "visitor", lambda *_: "owner")
    return app, loaded


def synthesis(ids):
    return {"summary": "The fault patterns suggest a targeted robustness check.",
        "hypotheses": [{"title": "Missingness handling may hide useful changes",
            "explanation": "Imputation may suppress changes that the warning model relies on.",
            "observation_ids": ids[:2],
            "alternative": "The pattern may instead reflect the chosen warning threshold."}],
        "gaps": ["Aggregate results do not show whether the same histories miss each warning."],
        "next_tests": [{"title": "Separate missingness from filled readings",
            "procedure": "Audit missing-reading flags and median imputation; replay late and missed warnings on development histories with the model fixed.",
            "expected_signal": "Recorded score crossings occur without an active warning.",
            "interpretation": "Recovery would support a missingness-handling explanation; no recovery would shift attention to timing and threshold sensitivity.",
            "observation_ids": ids[:2]}]}


def provider_synthesis(ids):
    output = synthesis(ids)
    output.pop("summary")
    for item in output["next_tests"]:
        item.pop("interpretation")
        item["if_signal_observed"] = "The recorded pattern points toward a persistence issue."
        item["if_signal_absent"] = "Absent crossings shift attention to preprocessing and score sensitivity."
    return output


def checked_fixture(output, packet):
    """Author current-contract mock tests; never convert immutable paid captures."""
    patterns = {row["id"]: row for row in packet["observations"]}
    for item in output["next_tests"]:
        item.update(model=next((patterns[id]["model"] for id in item["observation_ids"] if id in patterns), "model-1"),
            check_type="score_persistence", focus=item.pop("procedure"), signal="crossings_without_warning")
        for field in ("expected_signal", "if_signal_observed", "if_signal_absent"):
            value = item.pop(field)
            if "proves" in value or "Confirms" in value:
                item["focus"] = value
    return output


@pytest.mark.parametrize("candidate", ["logistic_regression/lr1", "xgboost_augmented/aug3"])
def test_structured_outcomes_accept_useful_wording_without_magic_words(deep_app, monkeypatch, candidate):
    app, _ = deep_app
    app.state.assistant.store.set_workspace_consent(True)
    calls = fake_provider(monkeypatch)
    with TestClient(app) as client:
        start = client.post("/api/assistant/analyses", json={**BODY, "candidates": [candidate]}, headers=HEADERS).json()
        record = completed(client, start["id"])
        assert record["result"]["mode"] == "ai"
        interpretation = record["result"]["deep_report"]["next_tests"][0]["interpretation"]
        assert "If observed:" in interpretation
        assert "Inspect crossing streaks" in interpretation
        assert "If absent:" in interpretation
        assert "Inspect whether scores remain below" in interpretation
        assert "if_signal_observed" not in json.dumps(record)  # Stored/public contract stays compatible.
    assert len(calls) == 1


@pytest.mark.parametrize("mutation", [
    lambda output: output["next_tests"][0].pop("if_signal_absent"),
    lambda output: output["next_tests"][0].update(if_signal_absent="   "),
    lambda output: output["next_tests"][0].update(if_signal_absent=output["next_tests"][0]["if_signal_observed"]),
    lambda output: output["next_tests"][0].update(if_signal_observed="This establishes the cause."),
])
def test_missing_empty_duplicate_or_decisive_outcomes_fail_without_retry(deep_app, monkeypatch, mutation):
    from app.assistant.deep import DeepProviderSynthesis, stored_synthesis, validate_synthesis
    from app.assistant.schemas import DeepObservation
    output = provider_synthesis(["pattern-1"])
    mutation(output)
    with pytest.raises(ValueError):
        value = stored_synthesis(DeepProviderSynthesis.model_validate(output))
        validate_synthesis(value, [DeepObservation(id="pattern-1", title="scope", text="record", source_ids=[])], {})


def test_provider_contract_requires_both_outcomes_and_bounds_stored_text():
    from app.assistant.deep import DeepProviderSynthesis, stored_synthesis
    schema = DeepProviderSynthesis.model_json_schema()
    assert "summary" not in schema["properties"]  # Provider cannot invent a measurement summary.
    test_schema = schema["$defs"]["DeepProviderTest"]
    assert {"if_signal_observed", "if_signal_absent"} <= set(test_schema["required"])
    assert "interpretation" not in test_schema["properties"]
    output = provider_synthesis(["pattern-1"])
    output["next_tests"][0].update(if_signal_observed="a" * 199 + ".", if_signal_absent="b" * 199 + ".")
    stored = stored_synthesis(DeepProviderSynthesis.model_validate(output))
    assert len(stored.next_tests[0].interpretation) <= 500
    assert "a" * 199 in stored.next_tests[0].interpretation and "b" * 199 in stored.next_tests[0].interpretation


@pytest.mark.parametrize("ids", [["pattern-1"], ["pattern-1", "pattern-10", "pattern-24"]])
def test_request_schema_constrains_every_citation_to_inspected_patterns(ids):
    from openai.lib._parsing._responses import type_to_text_format_param
    from pydantic import ValidationError

    from app.assistant.deep import provider_synthesis_schema
    model = provider_synthesis_schema(ids)
    schema = type_to_text_format_param(model)["schema"]
    for field in ("hypotheses", "next_tests"):
        ref = schema["properties"][field]["items"]["$ref"].split("/")[-1]
        item = schema["$defs"][ref]
        citation = item["properties"]["observation_ids"]["items"]
        assert citation.get("enum", [citation.get("const")]) == ids
        assert item["additionalProperties"] is False
        assert "observation_ids" in item["required"]
        output = provider_synthesis(ids)
        output[field][0]["observation_ids"] = ["pattern-999"]
        with pytest.raises(ValidationError):
            model.model_validate(output)
    assert isinstance(model.model_validate(provider_synthesis(ids)).model_dump(), dict)


def test_citation_schema_is_request_scoped_without_leaking_previous_choices():
    from pydantic import ValidationError

    from app.assistant.deep import provider_synthesis_schema
    first = provider_synthesis_schema(["pattern-1", "pattern-2"])
    second = provider_synthesis_schema(["pattern-1"])
    output = provider_synthesis(["pattern-2"])
    assert first.model_validate(output).hypotheses[0].observation_ids == ["pattern-2"]
    with pytest.raises(ValidationError):
        second.model_validate(output)


@pytest.mark.parametrize("wording", [
    "Temporal smoothing suppresses short excursions.",
    "The pattern is consistent with sensitivity to channel scaling.",
    "Threshold choice offers a competing explanation for the warning behavior.",
])
def test_mechanisms_are_framed_as_hypotheses_without_word_gates(deep_app, monkeypatch, wording):
    app, _ = deep_app
    app.state.assistant.store.set_workspace_consent(True)
    calls = fake_provider(monkeypatch, lambda output: output["hypotheses"][0].update(explanation=wording))
    with TestClient(app) as client:
        start = client.post("/api/assistant/analyses", json=BODY, headers=HEADERS).json()
        record = completed(client, start["id"])
        assert record["result"]["mode"] == "ai"
        explanation = record["result"]["deep_report"]["hypotheses"][0]["explanation"]
        assert explanation == "Possible explanation: " + wording
    assert len(calls) == 1


def test_deployment_uncertainty_is_not_confused_with_approval(deep_app, monkeypatch):
    app, _ = deep_app
    app.state.assistant.store.set_workspace_consent(True)
    calls = fake_provider(monkeypatch, lambda output: output.update(gaps=[
        "Performance under different deployment conditions remains unknown."]))
    with TestClient(app) as client:
        start = client.post("/api/assistant/analyses", json=BODY, headers=HEADERS).json()
        record = completed(client, start["id"])
        assert record["result"]["mode"] == "ai"
    assert len(calls) == 1


@pytest.mark.parametrize("candidate,filename", [
    ("xgboost_augmented/aug3", "deep_live_aug3_20261011.json"),
    ("logistic_regression/lr2", "deep_live_lr2_20261011.json"),
])
def test_captured_real_responses_render_and_convert_without_another_paid_call(deep_app, monkeypatch, candidate, filename):
    # Old free-form paid responses are not admitted as fresh typed diagnostics.
    # Historical stored output remains readable (covered separately).
    app, _ = deep_app
    app.state.assistant.store.set_workspace_consent(True)
    captured = json.loads((Path(__file__).parent / "fixtures" / filename).read_text(encoding="utf-8"))
    def replay(output):
        output.clear()
        output.update(captured)
    calls = fake_provider(monkeypatch, replay)
    with TestClient(app) as client:
        start = client.post("/api/assistant/analyses", json={**BODY, "candidates": [candidate]}, headers=HEADERS).json()
        record = completed(client, start["id"])
        assert record["result"]["mode"] == "evidence"
        assert record["result"]["deep_report"] is None and record["result"]["fallback_reason"]
        reused = client.post("/api/assistant/analyses?reuse=true", json={**BODY, "candidates": [candidate]}, headers=HEADERS).json()
        assert reused["id"] == record["id"]
    assert len(calls) == 1


@pytest.mark.parametrize("text,valid", [
    ("Audit missing sensor readings caused by dropout faults in development traces.", True),
    ("Audit missing readings caused by simulated dropout faults.", True),
    ("The fault is caused by a failing bearing.", False),
    ("Missing readings caused by dropout faults show that the problem is caused by a failing bearing.", False),
])
def test_simulated_dropout_is_distinguished_from_physical_diagnosis(deep_app, monkeypatch, text, valid):
    app, _ = deep_app
    app.state.assistant.store.set_workspace_consent(True)
    calls = fake_provider(monkeypatch, lambda output: output["next_tests"][0].update(procedure=text))
    with TestClient(app) as client:
        start = client.post("/api/assistant/analyses", json=BODY, headers=HEADERS).json()
        record = completed(client, start["id"])
        assert (record["result"]["mode"] == "ai") == valid
    assert len(calls) == 1


@pytest.mark.parametrize("field", ["hypotheses", "next_tests"])
def test_repeated_valid_citations_are_deduplicated_without_losing_order(deep_app, monkeypatch, field):
    app, _ = deep_app
    app.state.assistant.store.set_workspace_consent(True)
    def repeat(output):
        first, second = output[field][0]["observation_ids"]
        output[field][0]["observation_ids"] = [first, second, first, second]
    calls = fake_provider(monkeypatch, repeat)
    with TestClient(app) as client:
        start = client.post("/api/assistant/analyses", json=BODY, headers=HEADERS).json()
        record = completed(client, start["id"])
        assert record["result"]["mode"] == "ai"
        assert record["result"]["deep_report"][field][0]["observation_ids"] == ["pattern-1", "pattern-2"]
    assert len(calls) == 1


def test_real_sdk_serializes_scoped_schema_and_parses_augmented_report_offline(deep_app, monkeypatch):
    from openai import AsyncOpenAI as SDKClient

    from app.assistant import deep
    app, _ = deep_app
    app.state.assistant.store.set_workspace_consent(True)
    app.state.assistant.settings.assistant_timeout_seconds = 10  # Include cold SDK setup in this offline transport test.
    requests = []
    def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        packet = json.loads(payload["input"][-1]["content"])
        ids = [row["id"] for row in packet["observations"]]
        support_ids = [row["observation_id"] for section in packet["supporting_evidence"].values() for row in section.get("items", [])]
        schema = payload["text"]["format"]["schema"]
        for field in ("hypotheses", "next_tests"):
            ref = schema["properties"][field]["items"]["$ref"].split("/")[-1]
            assert schema["$defs"][ref]["properties"]["observation_ids"]["items"]["enum"] == ids + support_ids
        output = checked_fixture(provider_synthesis(ids), packet)
        output["next_tests"][0]["observation_ids"] = [ids[0], ids[0]]
        return httpx.Response(200, json={"id": "resp_fixture", "object": "response", "created_at": 0,
            "model": "fixture", "status": "completed", "error": None, "incomplete_details": None,
            "output": [{"id": "msg_fixture", "type": "message", "status": "completed", "role": "assistant",
                "content": [{"type": "output_text", "text": json.dumps(output), "annotations": []}]}]})
    def offline_client(**kwargs):
        assert kwargs["api_key"] == "mock-only" and kwargs["max_retries"] == 0
        return SDKClient(**kwargs, base_url="http://sdk-fixture.invalid/v1",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(deep, "AsyncOpenAI", offline_client)
    with TestClient(app) as client:
        start = client.post("/api/assistant/analyses", json={**BODY, "candidates": ["xgboost_augmented/aug3"]}, headers=HEADERS).json()
        record = completed(client, start["id"])
        assert record["result"]["mode"] == "ai", record["result"]["fallback_reason"]
        assert record["result"]["deep_report"]["next_tests"][0]["observation_ids"] == ["pattern-1"]
    assert len(requests) == 1 and requests[0]["store"] is False


def fake_provider(monkeypatch, mutate=None):
    from app.assistant import deep
    calls = []
    class Client:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0
            self.responses = self
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_):
            return None
        async def parse(self, **kwargs):
            calls.append(kwargs)
            packet = json.loads(kwargs["input"][-1]["content"])
            output = provider_synthesis([row["id"] for row in packet["observations"]])
            output["_mock_contract"] = True
            if mutate:
                mutate(output)
            if output.pop("_mock_contract", False):
                checked_fixture(output, packet)
            return SimpleNamespace(output_parsed=kwargs["text_format"].model_validate(output))
    monkeypatch.setattr(deep, "AsyncOpenAI", Client)
    return calls


BODY = {"task": "deep", "candidates": ["logistic_regression/lr1"]}
HEADERS = {"X-Sidekick-Request": "1"}


def completed(client, id):
    for _ in range(50):
        record = client.get(f"/api/assistant/analyses/{id}").json()
        if record["status"] != "running":
            return record
        # Synchronize with the TestClient event loop, without a paid retry.
        client.portal.call(asyncio.sleep, .01)
    pytest.fail("Mock investigation did not complete")


def test_deep_requires_permission_and_never_runs_in_replay(deep_app, monkeypatch):
    app, _ = deep_app
    calls = fake_provider(monkeypatch)
    with TestClient(app) as client:
        assert client.post("/api/assistant/analyses", json=BODY, headers=HEADERS).status_code == 403
        app.state.assistant.store.set_workspace_consent(True)
        app.state.assistant.settings.mode = "replay"
        assert client.post("/api/assistant/analyses", json=BODY, headers=HEADERS).status_code == 403
    assert calls == []


def test_one_request_cited_report_reuse_brief_and_revocation(deep_app, monkeypatch):
    app, loaded = deep_app
    calls = fake_provider(monkeypatch)
    original = loaded.model_dump_json()
    app.state.assistant.store.set_workspace_consent(True)
    with TestClient(app) as client:
        start = client.post("/api/assistant/analyses?reuse=true", json=BODY, headers=HEADERS)
        assert start.status_code == 200
        result = completed(client, start.json()["id"])
        assert result["result"]["mode"] == "ai"
        report = result["result"]["deep_report"]
        assert report["hypotheses"][0]["alternative"]
        assert report["summary"] == (f"Suggested focus: {report['next_tests'][0]['title'].rstrip('.')}. "
            "These explanations require checking against recorded evidence.")
        assert "median imputation" in report["next_tests"][0]["procedure"]
        observations = {row["id"] for row in report["observations"]}
        sources = {row["id"] for row in result["result"]["sources"]}
        assert all(set(row["source_ids"]) <= sources for row in report["observations"])
        assert set(report["hypotheses"][0]["observation_ids"]) <= observations
        again = client.post("/api/assistant/analyses?reuse=true", json=BODY, headers=HEADERS).json()
        assert again["id"] == result["id"]
        path = f"/api/assistant/analyses/{result['id']}"
        brief = client.post(path + "/review", headers=HEADERS).json()
        assert "Possible explanations" in brief["result"]["brief_draft"]
        assert report["next_tests"][0]["procedure"] in brief["result"]["brief_draft"]
        assert client.post(path + "/brief", headers=HEADERS, json={"text": "Edited deep report"}).status_code == 200
        exported = client.get(path + "/export")
        assert exported.status_code == 200
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            document = html.unescape(archive.read("review-brief.html").decode())
            assert "Possible explanations (tentative)" in document and report["next_tests"][0]["expected_signal"] in document
            assert "Edited deep report" in document
        client.post("/api/assistant/consent/workspace", headers=HEADERS, json={"allowed": False})
        revoked = client.get(path).json()
        assert revoked["result"]["deep_report"] is None
        assert "Edited deep report" not in json.dumps(revoked)
        assert client.get(path + "/export").status_code == 403
    assert len(calls) == 1 and calls[0]["store"] is False
    assert loaded.model_dump_json() == original


def test_evidence_packet_explains_protocol_using_only_recorded_boundaries(deep_app):
    from app.assistant.deep import collect_patterns
    from app.assistant.investigation import EvidenceTools
    _, loaded = deep_app
    loaded = loaded.model_copy(deep=True)
    loaded.config["min_useful_lead"] = 7
    loaded.config.pop("transition_band_end", None)
    _, packet, _ = collect_patterns(EvidenceTools(loaded, AnalysisRequest.model_validate(BODY)))
    assert packet["protocol_boundaries"]["min_useful_lead"] == 7
    assert packet["protocol_boundaries"]["transition_band_end"] is None  # No invented default.
    definitions = packet["metric_definitions"]
    assert "Undesirable alarm time" in definitions["early_alarm_burden"]
    assert "No failed cases does not mean every history was detected" in definitions["failed_cases"]
    assert "cannot establish the missing flag" in definitions["coverage_unknown"]
    assert "Never use reserved histories" in definitions["reserved_histories"]
    assert packet["recorded_facts"]["every_history_warned_in_time"] == all(row.metrics.detected == row.metrics.engines
        for row in EvidenceTools(loaded, AnalysisRequest.model_validate(BODY)).rows)


@pytest.mark.parametrize("bad", ["Made-up detection is 99%.", "See https://example.com", "This proves a physical failure cause.", "Ready for deployment.",
    "Deploy this model.", "The model is approved for field use.", "Deployment is safe."])
def test_unsupported_explanation_is_removed_without_retry(deep_app, monkeypatch, bad):
    app, _ = deep_app
    app.state.assistant.store.set_workspace_consent(True)
    calls = fake_provider(monkeypatch, lambda output: output["hypotheses"][0].update(explanation=bad))
    with TestClient(app) as client:
        start = client.post("/api/assistant/analyses", json=BODY, headers=HEADERS).json()
        record = completed(client, start["id"])
        report = record["result"]["deep_report"]
        assert record["result"]["mode"] == "ai" and report
        assert report["hypotheses"] == [] and report["next_tests"]
        assert "No AI explanation passed verification" in " ".join(report["limitations"])
    assert len(calls) == 1


def test_malformed_report_has_safe_reason_without_provider_text(deep_app, monkeypatch):
    app, _ = deep_app
    app.state.assistant.store.set_workspace_consent(True)
    calls = fake_provider(monkeypatch, lambda output: output["hypotheses"][0].update(explanation="private-provider-text " * 40))
    with TestClient(app) as client:
        start = client.post("/api/assistant/analyses", json=BODY, headers=HEADERS).json()
        record = completed(client, start["id"])
        assert record["result"]["mode"] == "evidence"
        assert "required format" in record["result"]["fallback_reason"]
        assert "private-provider-text" not in json.dumps(record)
    assert len(calls) == 1


def test_two_models_and_invalid_history_scope():
    assert len(AnalysisRequest(task="deep", candidates=["a", "b"]).candidates) == 2
    with pytest.raises(ValueError):
        AnalysisRequest(task="deep", candidates=["a"], equipment_id="private-history")


def test_saved_report_survives_restart_key_removal_and_regular_brief_reuses_it(deep_app, monkeypatch):
    app, _ = deep_app
    calls = fake_provider(monkeypatch)
    settings = app.state.assistant.settings
    app.state.assistant.store.set_workspace_consent(True)
    with TestClient(app) as client:
        start = client.post("/api/assistant/analyses?reuse=true", json=BODY, headers=HEADERS).json()
        record = completed(client, start["id"])
        assert record["output_currency"] == "current"
        assert record["result"]["mode"] == "ai"
        app.state.assistant = AssistantService(settings)
        settings.openai_api_key = ""
        reopened = client.post("/api/assistant/analyses?reuse=true", json=BODY, headers=HEADERS).json()
        assert reopened["id"] == record["id"] and reopened["result"]["deep_report"]
        brief = client.post("/api/assistant/analyses?reuse=true", json={**BODY, "task": "brief"}, headers=HEADERS).json()
        assert brief["id"] == record["id"] and brief["context"]["task"] == "brief"
        assert "Possible explanations" in brief["result"]["brief_draft"]
        assert client.get(f"/api/assistant/analyses/{record['id']}").json()["output_currency"] == "current"
        settings.assistant_model = "changed-fixture-model"
        assert client.get(f"/api/assistant/analyses/{record['id']}").json()["output_currency"] == "historical"
    assert len(calls) == 1


def test_pattern_scope_aliases_and_missing_measurements(deep_app):
    from app.assistant.deep import MAX_PATTERNS, collect_patterns
    from app.assistant.investigation import EvidenceTools
    _, bundle = deep_app
    scoped = bundle.model_copy(deep=True)
    rows = [row for row in scoped.scenario_results if row.required and row.fault and f"{row.candidate.value}/{row.config_id}" == BODY["candidates"][0] and row.partition.value == "out_of_fold"]
    rows[0].fault.sensor = "private-channel-name"
    rows[0].metrics.early_alarm_burden = None
    rows[0].coverage_complete = None
    tools = EvidenceTools(scoped, AnalysisRequest.model_validate(BODY))
    observations, packet, _ = collect_patterns(tools)
    serialized = json.dumps(packet)
    assert "private-channel-name" not in serialized
    assert "lr1" not in serialized  # The family is public; configuration labels stay local.
    assert len(observations) <= MAX_PATTERNS and packet["inspected_cases"] == len(rows)
    assert any(row["coverage"] == "unknown" for row in packet["observations"])
    assert any(not row["early_alarm_available"] for row in packet["observations"])
    assert all(source.partition.value == "out_of_fold" and source.candidate in BODY["candidates"] for source in tools.result.sources)


@pytest.mark.parametrize("field", ["hypotheses", "next_tests"])
def test_bad_citations_fall_back(deep_app, monkeypatch, field):
    app, _ = deep_app
    app.state.assistant.store.set_workspace_consent(True)
    calls = fake_provider(monkeypatch, lambda output: output[field][0].update(observation_ids=["invented-pattern"]))
    with TestClient(app) as client:
        record = client.post("/api/assistant/analyses", json=BODY, headers=HEADERS).json()
        result = completed(client, record["id"])
        assert result["result"]["mode"] == "evidence" and result["result"]["fallback_reason"]
        assert "citation" in result["result"]["fallback_reason"].lower()
    assert len(calls) == 1


def test_scoped_aliases_with_shared_prefixes_and_diagnostic_checks_are_valid():
    from app.assistant.deep import DeepSynthesis, validate_synthesis
    from app.assistant.schemas import DeepObservation
    observations = [DeepObservation(id="pattern-1", title="Recorded pattern", text="Recorded evidence.", source_ids=["source-a"])]
    output = synthesis(["pattern-1"])
    output["summary"] = "Channel-10 may respond differently from channel-1 in Model-1."
    output["next_tests"][0]["title"] = "Run a diagnostic check"
    validate_synthesis(DeepSynthesis.model_validate(output), observations,
                       {"channel-1": "sensor_a", "channel-10": "sensor_b", "model-1": "model_a"})


@pytest.mark.parametrize("text", [
    "channel-100 may behave differently.", "channel-10 has 99% detection.",
    "This diagnoses a physical failure.", "The diagnostic check proves the cause.",
])
def test_alias_repair_still_rejects_unknown_aliases_numbers_and_diagnoses(text):
    from app.assistant.deep import DeepSynthesis, validate_synthesis
    from app.assistant.schemas import DeepObservation
    observations = [DeepObservation(id="pattern-1", title="Recorded pattern", text="Recorded evidence.", source_ids=["source-a"])]
    output = synthesis(["pattern-1"])
    output["summary"] = text
    with pytest.raises(ValueError):
        validate_synthesis(DeepSynthesis.model_validate(output), observations,
                           {"channel-1": "sensor_a", "channel-10": "sensor_b"})


def test_provider_aliases_resolve_after_whole_token_validation(deep_app, monkeypatch):
    app, _ = deep_app
    app.state.assistant.store.set_workspace_consent(True)
    def mutate(output):
        output["hypotheses"][0]["explanation"] = "Channel-10 may respond differently from channel-1."
        output["next_tests"][0]["title"] = "Run a diagnostic check"
    calls = fake_provider(monkeypatch, mutate)
    with TestClient(app) as client:
        start = client.post("/api/assistant/analyses", json=BODY, headers=HEADERS).json()
        record = completed(client, start["id"])
        assert record["result"]["mode"] == "ai"
        assert "Channel-10" not in record["result"]["deep_report"]["hypotheses"][0]["explanation"]
        assert "channel-1" not in record["result"]["deep_report"]["hypotheses"][0]["explanation"]
    assert len(calls) == 1


def test_active_deep_and_brief_admissions_share_one_job(deep_app, monkeypatch):
    from app.assistant import deep
    app, _ = deep_app
    app.state.assistant.settings.assistant_timeout_seconds = 30
    app.state.assistant.store.set_workspace_consent(True)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    class Client:
        def __init__(self, **_):
            self.responses = self
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_):
            return None
        async def parse(self, **kwargs):
            calls.append(kwargs)
            entered.set()
            await release.wait()
            packet = json.loads(kwargs["input"][-1]["content"])
            return SimpleNamespace(output_parsed=kwargs["text_format"].model_validate(checked_fixture(provider_synthesis([row["id"] for row in packet["observations"]]), packet)))
    monkeypatch.setattr(deep, "AsyncOpenAI", Client)
    with TestClient(app) as client:
        start = client.post("/api/assistant/analyses?reuse=true", json=BODY, headers=HEADERS).json()
        client.portal.call(entered.wait)
        again = client.post("/api/assistant/analyses?reuse=true", json=BODY, headers=HEADERS).json()
        brief = client.post("/api/assistant/analyses?reuse=true", json={**BODY, "task": "brief"}, headers=HEADERS).json()
        assert start["id"] == again["id"] == brief["id"] and brief["status"] == "running"
        client.portal.call(release.set)
        assert completed(client, start["id"])["result"]["mode"] == "ai"
    assert len(calls) == 1


@pytest.mark.parametrize("mutation", [
    lambda output: output.update(gaps=["Same gap.", "Same gap."]),
    lambda output: output["hypotheses"][0].update(explanation="   "),
    lambda output: output["next_tests"][0].update(if_signal_observed="This proves the cause."),
    lambda output: output["next_tests"][0].update(if_signal_observed="Confirms threshold tuning is the limiting factor."),
    lambda output: output["hypotheses"][0].update(explanation="The model uses augmented input features to achieve near-perfect detection."),
    lambda output: output["hypotheses"][0].update(explanation="Augmented feature representation explains the warning changes."),
])
def test_nonuseful_or_overconfident_reports_fail_safely(deep_app, monkeypatch, mutation):
    app, _ = deep_app
    app.state.assistant.store.set_workspace_consent(True)
    calls = fake_provider(monkeypatch, mutation)
    with TestClient(app) as client:
        start = client.post("/api/assistant/analyses", json=BODY, headers=HEADERS).json()
        record = completed(client, start["id"])
        report = record["result"]["deep_report"]
        if report:
            # Independent feasible questions can survive a rejected explanation.
            assert report["hypotheses"] == [] and report["next_tests"]
            assert "No AI explanation passed verification" in " ".join(report["limitations"])
        else:
            assert record["result"]["mode"] == "evidence"
    assert len(calls) == 1


def test_captured_enriched_response_rejects_invented_features_and_confirmation():
    from app.assistant.deep import DeepProviderSynthesis, DeepVerificationError, stored_synthesis, validate_synthesis
    from app.assistant.schemas import DeepObservation
    captured = json.loads((Path(__file__).parent / "fixtures" / "deep_rejected_feature_claims_20261011.json").read_text(encoding="utf-8"))
    observations = [DeepObservation(id=id, title="Original scope", text="Recorded summary", source_ids=[])
                    for id in captured["inspected_ids"]]
    with pytest.raises(DeepVerificationError):
        validate_synthesis(stored_synthesis(DeepProviderSynthesis.model_validate(captured["parsed"])), observations, captured["aliases"])


def test_negative_confirmation_boundary_does_not_hide_later_invention():
    from app.assistant.deep import DeepProviderSynthesis, DeepVerificationError, stored_synthesis, validate_synthesis
    from app.assistant.schemas import DeepObservation
    observations = [DeepObservation(id="pattern-a", title="Recorded pattern", text="scope", source_ids=[])]
    output = provider_synthesis(["pattern-a"])
    output["gaps"] = ["A proposed check cannot confirm a cause."]
    validate_synthesis(stored_synthesis(DeepProviderSynthesis.model_validate(output)), observations, {})
    output["gaps"] = ["No historical preprocessing details are available to confirm imputation differences."]
    validate_synthesis(stored_synthesis(DeepProviderSynthesis.model_validate(output)), observations, {})
    output["gaps"] = ["A proposed check cannot confirm a cause, but near-perfect detection is established."]
    with pytest.raises(DeepVerificationError):
        validate_synthesis(stored_synthesis(DeepProviderSynthesis.model_validate(output)), observations, {})


def test_captured_comparison_retains_safe_check_and_omits_unsupported_sections(deep_app, monkeypatch):
    app, _ = deep_app
    captured = json.loads((Path(__file__).parent / "fixtures" / "deep_partial_comparison_20261011.json").read_text(encoding="utf-8"))
    def replace_output(output):
        output.clear()
        output.update(captured["parsed"])
    calls = fake_provider(monkeypatch, replace_output)
    app.state.assistant.store.set_workspace_consent(True)
    body = {**BODY, "candidates": ["xgboost_augmented/aug3", "logistic_regression/lr2"]}
    with TestClient(app) as client:
        record = completed(client, client.post("/api/assistant/analyses", json=body, headers=HEADERS).json()["id"])
        assert record["result"]["mode"] == "evidence" and record["result"]["deep_report"] is None
    assert len(calls) == 1  # No retries or silent procedure conversion.


@pytest.mark.parametrize("reference", ["patterns 1-2", "pattern 99", "patterns 1.5", "pattern 1 %"])
def test_pattern_prose_cannot_smuggle_unknown_references_or_measurements(reference):
    from app.assistant.deep import DeepProviderSynthesis, verified_synthesis
    from app.assistant.schemas import DeepObservation
    output = provider_synthesis(["pattern-1"])
    output["next_tests"][0]["procedure"] = f"Inspect {reference} with the model fixed."
    observations = [DeepObservation(id="pattern-1", title="Recorded", text="Scope", source_ids=[])]
    with pytest.raises(ValueError):
        verified_synthesis(DeepProviderSynthesis.model_validate(output), observations, {})


def test_comparison_runs_one_request_and_reuses_exact_order(deep_app, monkeypatch):
    app, _ = deep_app
    app.state.assistant.store.set_workspace_consent(True)
    calls = fake_provider(monkeypatch)
    body = {**BODY, "candidates": ["logistic_regression/lr1", "xgboost_augmented/aug1"]}
    with TestClient(app) as client:
        start = client.post("/api/assistant/analyses?reuse=true", json=body, headers=HEADERS)
        assert start.status_code == 200, start.text
        record = completed(client, start.json()["id"])
        assert record["result"]["mode"] == "ai"
        packet = json.loads(calls[0]["input"][-1]["content"])
        assert {row["model"] for row in packet["observations"]} == {"model-1", "model-2"}
        assert len(calls) == 1


@pytest.mark.parametrize("candidates", [
    ["xgboost_augmented/aug3", "logistic_regression/lr2"],
    ["logistic_regression/lr2", "xgboost_augmented/aug3"],
])
def test_bounded_comparison_includes_fault_evidence_for_both_selected_models(deep_app, candidates):
    from collections import Counter
    from app.assistant.deep import MAX_PATTERNS, collect_patterns
    from app.assistant.investigation import EvidenceTools
    _, bundle = deep_app
    context = AnalysisRequest.model_validate({**BODY, "candidates": candidates})
    tools = EvidenceTools(bundle, context)
    _, packet, _ = collect_patterns(tools)
    counts = Counter(row["model"] for row in packet["observations"])
    assert counts == {"model-1": MAX_PATTERNS // 2, "model-2": MAX_PATTERNS // 2}
    assert len(packet["observations"]) == MAX_PATTERNS
    assert len(json.dumps(packet, separators=(",", ":")).encode()) <= 40000
    assert packet == collect_patterns(EvidenceTools(bundle, context))[1]
    assert all(model["provided_patterns"] == 12 and model["available_patterns"] == 48
               for model in packet["models"])


def test_comparison_spills_unused_slots_without_inventing_model_evidence(deep_app):
    from collections import Counter
    from app.assistant.deep import collect_patterns
    from app.assistant.investigation import EvidenceTools
    _, bundle = deep_app
    context = AnalysisRequest.model_validate({**BODY, "candidates": ["xgboost_augmented/aug3", "logistic_regression/lr2"]})
    tools = EvidenceTools(bundle, context)
    # Keep one recorded aug3 pattern, alongside all lr2 rows.
    first = next(row for row in tools.rows if row.config_id == "aug3")
    tools.rows = [row for row in tools.rows if row.config_id == "lr2" or
                  (row.fault.sensor, row.fault.kind, row.fault.duration) ==
                  (first.fault.sensor, first.fault.kind, first.fault.duration)]
    _, packet, _ = collect_patterns(tools)
    assert Counter(row["model"] for row in packet["observations"]) == {"model-1": 1, "model-2": 23}
    tools.rows = [row for row in tools.rows if row.config_id == "lr2"]
    _, packet, _ = collect_patterns(tools)
    assert Counter(row["model"] for row in packet["observations"]) == {"model-2": 24}
    assert packet["models"][0]["provided_patterns"] == packet["models"][0]["available_patterns"] == 0


def test_exact_rejected_response_accepts_valid_references_in_original_citation_scope():
    from app.assistant.deep import DeepProviderSynthesis, stored_synthesis, validate_synthesis
    from app.assistant.schemas import DeepObservation
    captured = json.loads((Path(__file__).parent / "fixtures" /
        "deep_rejected_hypothesis_references_20261011.json").read_text(encoding="utf-8"))
    # Validator regression only: these IDs belong to the original v7 packet.
    # Never reinterpret the old response against the newly balanced packet.
    observations = [DeepObservation(id=id, title="Original captured pattern", text="Original scope", source_ids=[])
                    for id in captured["inspected_ids"]]
    output = stored_synthesis(DeepProviderSynthesis.model_validate(captured["parsed"]))
    validate_synthesis(output, observations, {alias: alias for alias in captured["aliases"]}, fault_kinds={"dropout", "stuck", "drift"})
    assert "hypothesis 1" in output.next_tests[0].interpretation
    assert "hypothesis 2 alternative" in output.next_tests[1].interpretation
    assert "hypothesis 3" in output.next_tests[2].interpretation


@pytest.mark.parametrize("label,candidates", [
    ("balanced-pair", ["xgboost_augmented/aug3", "logistic_regression/lr2"]),
    ("balanced-reversed", ["logistic_regression/lr2", "xgboost_augmented/aug3"]),
])
def test_captured_comparison_current_verification_and_reuse_without_extra_calls(deep_app, monkeypatch, label, candidates):
    from app.assistant.deep import collect_patterns
    from app.assistant.investigation import EvidenceTools
    app, bundle = deep_app
    app.state.assistant.store.set_workspace_consent(True)
    context = {**BODY, "candidates": candidates}
    captured = json.loads((Path(__file__).parent / "fixtures" /
        f"deep_live_comparison_{label}_20261011.json").read_text(encoding="utf-8"))
    assert collect_patterns(EvidenceTools(bundle, AnalysisRequest.model_validate(context)))[1] == captured["packet"]
    def replay(output):
        output.clear()
        output.update(captured["parsed"])
    calls = fake_provider(monkeypatch, replay)
    with TestClient(app) as client:
        record = completed(client, client.post("/api/assistant/analyses", json=context, headers=HEADERS).json()["id"])
        assert record["result"]["mode"] == "evidence" and record["result"]["deep_report"] is None
        again = client.post("/api/assistant/analyses?reuse=true", json=context, headers=HEADERS).json()
        assert again["id"] == record["id"]
    assert len(calls) == 1


@pytest.mark.parametrize("reference,accepted", [
    ("hypothesis 1", True), ("HYPOTHESIS 1 alternative", True),
    ("hypothesis 2", False), ("hypothesis 1 has 99% detection", False),
    ("hypothesis 1.5", False), ("hypothesis 1%", False),
])
def test_numbered_hypothesis_reference_is_not_a_measurement(deep_app, monkeypatch, reference, accepted):
    from app.assistant.deep import DeepProviderSynthesis, stored_synthesis, validate_synthesis
    from app.assistant.schemas import DeepObservation
    output = provider_synthesis(["pattern-1"])
    output["next_tests"][0]["if_signal_observed"] = f"Recovery would support the proposed explanation ({reference})."
    def validate():
        validate_synthesis(stored_synthesis(DeepProviderSynthesis.model_validate(output)),
            [DeepObservation(id="pattern-1", title="scope", text="record", source_ids=[])], {})
    if accepted:
        validate()
    else:
        with pytest.raises(ValueError):
            validate()


def test_long_deep_brief_stays_saveable_without_cutting_report(deep_app):
    from app.assistant.deep import collect_patterns
    from app.assistant.evidence import with_brief
    from app.assistant.investigation import EvidenceTools
    from app.assistant.schemas import DeepReport
    _, bundle = deep_app
    context = AnalysisRequest.model_validate(BODY)
    tools = EvidenceTools(bundle, context)
    observations, packet, _ = collect_patterns(tools)
    output = synthesis([row.id for row in observations])
    output["summary"] = "s" * 500
    output["hypotheses"] *= 3
    output["next_tests"] *= 3
    for item in output["hypotheses"]:
        item.update(title="h" * 120, explanation="e" * 700, alternative="a" * 500)
    for item in output["next_tests"]:
        item.update(title="t" * 120, procedure="p" * 700, expected_signal="s" * 500, interpretation="i" * 500)
    output["gaps"] = ["g" * 500] * 3
    report = DeepReport(**output, observations=observations, inspected_cases=packet["inspected_cases"], pattern_count=packet["total_patterns"], latency_seconds=0, limitations=["Tentative hypotheses only."])
    result = tools.result.model_copy(update={"deep_report": report})
    brief = with_brief(result, context.model_copy(update={"task": "brief"}))
    assert len(brief.brief_draft) <= 12000
    assert "compact brief" in brief.brief_draft
    assert brief.deep_report == report and len(report.next_tests) == 3
    assert report.next_tests[0].procedure in brief.brief_draft
