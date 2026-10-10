import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from openai.types.responses import ResponseFunctionToolCall

from app.assistant.agent import InvestigationChoices, investigate
from app.assistant.investigation import EvidenceTools
from app.assistant.schemas import AnalysisRequest
from app.evidence.bundle import load_bundle

SETTINGS = SimpleNamespace(openai_api_key="test", assistant_model="test", llm_max_tool_calls=8)


@pytest.fixture
def tools():
    bundle = load_bundle(Path(__file__).resolve().parents[1] / "evidence/bundle.json")
    return EvidenceTools(bundle, AnalysisRequest(task="investigate", candidates=["logistic_regression/lr2"]))


def fakeClient(monkeypatch, tools, requests=None, choices=None):
    packets = []
    requests = requests if requests is not None else [
        ("get_model_metrics", {"model": "model-1"}),
        ("list_fault_cases", {"model": "model-1", "order": "failed", "limit": 1}),
        ("inspect_fault_case", "first-case"),
    ]

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0
            self.responses = self
            self.index = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def create(self, **kwargs):
            packets.append(json.dumps(kwargs))
            assert kwargs["store"] is False and kwargs["parallel_tool_calls"] is False
            assert kwargs["max_output_tokens"] == 700
            if self.index >= len(requests):
                return SimpleNamespace(output=[SimpleNamespace(type="message", text="Deploy this model. sensor_11 caused a bearing failure.")])
            name, args = requests[self.index]
            if args == "first-case":
                model, case = next(iter(tools.listedCases))
                args = {"model": model, "case": case}
            self.index += 1
            return SimpleNamespace(output=[ResponseFunctionToolCall(type="function_call", call_id=f"call-{self.index}", name=name, arguments=json.dumps(args))])

        async def parse(self, **kwargs):
            packets.append(json.dumps(kwargs["input"]))
            assert kwargs["store"] is False
            selected = choices or InvestigationChoices(finding_ids=[f"inspected-model-1-{next(iter(tools.listedCases))[1]}"],
                claim_ids=[id for id in tools.claims if id.startswith(("detection-", "loss-"))], action_id=None)
            return SimpleNamespace(output_parsed=selected)

    monkeypatch.setattr("app.assistant.agent.AsyncOpenAI", Client)
    return packets


def test_live_agent_inspects_evidence_and_never_displays_arbitrary_text(monkeypatch, tools):
    original = tools.bundle.model_dump_json()
    packets = fakeClient(monkeypatch, tools)
    result = asyncio.run(investigate(tools, SETTINGS))
    assert result.mode == "ai" and result.interpretation is None
    assert [call.name for call in result.investigation] == ["get_model_metrics", "list_fault_cases", "inspect_fault_case"]
    assert "39 fewer timely warnings" in " ".join(claim.text for claim in result.assessment)
    assert tools.bundle.model_dump_json() == original
    text = " ".join(packets)
    assert "sensor_" not in text and "logistic_regression" not in text and "/comparison" not in text
    assert "Deploy this model" not in result.model_dump_json()
    assert '"tool_choice": {"type": "function", "name": "get_model_metrics"}' in packets[0]


@pytest.mark.parametrize("task", ["compare", "warning"])
def test_context_tasks_stop_after_the_required_tool_instead_of_repeating_calls(monkeypatch, tools, task):
    bundle = tools.bundle
    if task == "compare":
        context = AnalysisRequest(task="compare", candidates=["logistic_regression/lr2", "xgboost/xgb1"])
        name, finding, claims = "compare_models", "overview", ["comparison-limits"]
    else:
        series = next(s for s in bundle.replay_series if s.partition.value == "out_of_fold" and s.points)
        context = AnalysisRequest(task="warning", candidates=[f"{series.candidate.value}/{series.config_id}"],
            scenario_id=series.scenario_id, equipment_id=series.equipment_id, cycle=series.points[0].cycle)
        name, finding, claims = "get_warning_events", None, ["warning-state"]
    scoped = EvidenceTools(bundle, context)
    if finding is None:
        finding = scoped.result.findings[0].id
    packets = fakeClient(monkeypatch, scoped, [(name, {}), ("train_model", {})],
        InvestigationChoices(finding_ids=[finding], claim_ids=claims, action_id=None))
    result = asyncio.run(investigate(scoped, SETTINGS))
    assert [call.name for call in result.investigation] == [name]
    assert len(packets) == 1  # One structured selection, no tool-planning requests.
    inspected = json.loads(json.loads(packets[0])[2]["content"])["server_inspection"]
    assert inspected["name"] == name
    assert all(call.label.startswith("Server inspection · ") for call in result.investigation)


@pytest.mark.parametrize("name,args", [
    ("train_model", {}), ("get_model_metrics", {"model": "model-2"}),
    ("get_model_metrics", {"model": "model-1", "experiment_id": "other"}),
    ("inspect_fault_case", {"model": "model-1", "case": "case-1"}),
])
def test_agent_rejects_unavailable_or_out_of_scope_tools(monkeypatch, tools, name, args):
    fakeClient(monkeypatch, tools, [(name, args)])
    with pytest.raises(ValueError):
        asyncio.run(investigate(tools, SETTINGS))


@pytest.mark.parametrize("field,value", [("finding_ids", ["unseen"]), ("claim_ids", ["invented"]), ("action_id", "https://evil.test")])
def test_unverified_final_selection_is_rejected(monkeypatch, tools, field, value):
    choices = InvestigationChoices(finding_ids=["f0"], claim_ids=["limits-model-1"], action_id=None).model_copy(update={field: value})
    fakeClient(monkeypatch, tools, choices=choices)
    with pytest.raises(ValueError):
        asyncio.run(investigate(tools, SETTINGS))


def test_agent_must_inspect_a_case_not_only_rank_metrics(monkeypatch, tools):
    fakeClient(monkeypatch, tools, [("get_model_metrics", {"model": "model-1"})])
    with pytest.raises(ValueError, match="required evidence"):
        asyncio.run(investigate(tools, SETTINGS))


def test_tool_limit_and_input_budget_fail_closed(monkeypatch, tools):
    fakeClient(monkeypatch, tools)
    settings = SimpleNamespace(**{**vars(SETTINGS), "llm_max_tool_calls": 2})
    with pytest.raises(ValueError):
        asyncio.run(investigate(tools, settings))
    tools = tools.fresh()
    fakeClient(monkeypatch, tools)
    monkeypatch.setattr("app.assistant.agent.MAX_HISTORY_BYTES", 20)
    with pytest.raises(ValueError, match="input budget"):
        asyncio.run(investigate(tools, SETTINGS))


def test_local_fallback_does_not_authorize_unseen_live_cases(tools):
    tools.local()
    fresh = tools.fresh()
    assert not fresh.listedCases and not fresh.claims and not fresh.calls
    assert not fresh.result.assessment and not fresh.result.investigation
