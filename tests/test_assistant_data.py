import json
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.assistant.data_review import DataTools, reviewData
from app.assistant.agent import InvestigationChoices, investigate
from app.assistant.schemas import AnalysisRequest
from app.data.synthetic import make_synthetic_dataset
from app.experiments.datasets import register
from app.experiments.store import Workspace


@pytest.fixture
def dataset(tmp_path):
    workspace = Workspace(tmp_path)
    id = str(uuid4())
    path = workspace.directory("datasets", id) / "data.csv"
    path.parent.mkdir(parents=True)
    frame = make_synthetic_dataset().frame
    frame.to_csv(path, index=False)
    record = register(workspace, path, id, "private-factory.csv")
    return workspace, record, frame


def toolsFor(workspace, context):
    result, descriptors, columns = reviewData(workspace, context)
    return DataTools(result, context, descriptors, columns)


def test_mapping_review_is_read_only_and_cloud_packet_contains_no_headers(dataset):
    workspace, record, _ = dataset
    before = workspace.get("datasets", record.dataset_id)
    context = AnalysisRequest(task="data", dataset_id=record.dataset_id, mapping=record.mapping)
    tools = toolsFor(workspace, context)
    checks = tools.call("get_dataset_checks", {})
    mapping = tools.call("suggest_column_mapping", {})
    packet = json.dumps({"intro": tools.intro(), "checks": checks, "mapping": mapping})
    assert "sensor_" not in packet and "equipment_id\": \"column" in packet
    assert "private-factory" not in packet and record.dataset_id not in packet and "/new" not in packet
    result = tools.finish(["data-validation", "data-mapping"], checks["claims"][:2] + mapping["claims"], None, None)
    assert result.suggested_mapping and result.assessment
    assert workspace.get("datasets", record.dataset_id) == before
    with workspace.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM experiments").fetchone()[0] == 0


def test_unknown_failure_histories_remain_blocked(dataset):
    workspace, record, frame = dataset
    path = workspace.directory("datasets", record.dataset_id) / "data.csv"
    frame.drop(columns=["failure_cycle"]).to_csv(path, index=False)
    record = register(workspace, path, record.dataset_id, "data.csv")
    result = toolsFor(workspace, AnalysisRequest(task="data", dataset_id=record.dataset_id, mapping=record.mapping)).local()
    assert result.findings[0].tone == "danger"
    assert "Confirm that every history reaches failure" in result.findings[0].detail
    assert workspace.get("datasets", record.dataset_id)["confirmed"] is False


def test_invalid_roles_are_explained_and_drafts_do_not_change_fingerprint(dataset):
    workspace, record, _ = dataset
    mapping = record.mapping.model_copy(update={"cycle_index": record.mapping.equipment_id})
    result = toolsFor(workspace, AnalysisRequest(task="data", dataset_id=record.dataset_id, mapping=mapping)).local()
    assert result.findings[0].tone == "danger"
    valid = toolsFor(workspace, AnalysisRequest(task="data", dataset_id=record.dataset_id, mapping=record.mapping)).local()
    assert result.evidence_digest != valid.evidence_digest
    assert valid.findings[0].tone == "success"


def test_data_review_rejects_mixed_model_and_dataset_contexts():
    with pytest.raises(ValueError):
        AnalysisRequest(task="data", dataset_id="dataset", candidates=["xgboost/xgb1"])


def test_nonblocking_missing_readings_are_explained_in_assessment(dataset):
    workspace, record, frame = dataset
    path = workspace.directory("datasets", record.dataset_id) / "data.csv"
    frame.loc[frame.index[::10], record.mapping.sensors[0]] = float("nan")
    frame.to_csv(path, index=False)
    tools = toolsFor(workspace, AnalysisRequest(task="data", dataset_id=record.dataset_id, mapping=record.mapping))
    result = tools.local()
    assert result.findings[0].tone == "success"
    assert any("missing readings" in claim.text and "training medians" in claim.text for claim in result.assessment)
    assert "sensor_" not in str(tools.claim_catalog())
    assert not workspace.get("datasets", record.dataset_id)["confirmed"]


def test_live_selection_cannot_hide_readiness_or_a_quality_warning(dataset):
    workspace, record, frame = dataset
    path = workspace.directory("datasets", record.dataset_id) / "data.csv"
    frame.loc[frame.index[::10], record.mapping.sensors[0]] = float("nan")
    frame.to_csv(path, index=False)
    tools = toolsFor(workspace, AnalysisRequest(task="data", dataset_id=record.dataset_id, mapping=record.mapping))
    tools.call("get_dataset_checks", {})
    packet = tools.call("suggest_column_mapping", {})
    result = tools.finish(packet["finding_ids"], packet["claims"], None, "test")
    assert [claim.id for claim in result.assessment] == ["data-readiness", "data-issue-data-missing_values", "mapping-review"]


def test_data_review_inspects_locally_then_uses_one_selection_request(dataset, monkeypatch):
    workspace, record, _ = dataset
    tools = toolsFor(workspace, AnalysisRequest(task="data", dataset_id=record.dataset_id, mapping=record.mapping))
    requests = []

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0
            self.responses = self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def create(self, **kwargs):
            raise AssertionError("Data review must not pay for predetermined tool planning")

        async def parse(self, **kwargs):
            requests.append(kwargs)
            return SimpleNamespace(output_parsed=InvestigationChoices(
                finding_ids=["data-validation", "data-mapping"], claim_ids=["mapping-review"], action_id=None))

    monkeypatch.setattr("app.assistant.agent.AsyncOpenAI", Client)
    settings = SimpleNamespace(openai_api_key="fixture", assistant_model="fixture", llm_max_tool_calls=8)
    result = asyncio.run(investigate(tools, settings))
    assert len(requests) == 1
    assert [call.name for call in result.investigation] == ["get_dataset_checks", "suggest_column_mapping"]
    assert all(call.label.startswith("Server inspection · ") for call in result.investigation)
    packet = json.dumps(requests[0]["input"])
    assert "private-factory" not in packet and record.dataset_id not in packet and "sensor_" not in packet
    assert result.mode == "ai" and len(result.assessment) <= 3
