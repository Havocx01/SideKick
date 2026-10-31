"""Offline regressions from live Nemotron deep-investigation replies (prompt v20)."""
import asyncio
import json
from pathlib import Path

import pytest

from app.assistant import deep
from app.assistant.investigation import EvidenceTools
from app.assistant.schemas import AnalysisRequest
from app.config import Settings, get_settings
from app.evidence.bundle import load_bundle

CAPTURED = json.loads((Path(__file__).parent / "fixtures/nemotron-deep-replies.json").read_text(encoding="utf-8"))["cases"]
SETTINGS = Settings(mode="full", assistant_provider="nebius", nebius_api_key="mock", assistant_model="nvidia/nemotron-3-super-120b-a12b", assistant_live_enabled=True)


def replay(case, monkeypatch, reply=None):
    async def respond(client, settings, *, response_model, **kwargs):
        return response_model.model_validate(reply or case["reply"])
    monkeypatch.setattr(deep, "request_structured", respond)
    tools = EvidenceTools(load_bundle(get_settings().bundle_path), AnalysisRequest(task="deep", candidates=case["candidates"]))
    return asyncio.run(deep.investigate_deep(tools, SETTINGS))


@pytest.mark.parametrize("index", [0, 1])
def test_non_breaking_hyphens_in_aliases_no_longer_reject_a_reply(index, monkeypatch):
    case = CAPTURED[index]
    assert "‑" in json.dumps(case["reply"], ensure_ascii=False)
    report = replay(case, monkeypatch).deep_report
    text = json.dumps(report.model_dump(mode="json"), ensure_ascii=False)
    assert report.explanation_status == "retained" and report.next_tests and "‑" not in text
    assert "model-1" not in text and "Logistic regression" in text


def test_path_like_gaps_are_dropped_for_sidekicks_own_wording(monkeypatch):
    report = replay(CAPTURED[0], monkeypatch).deep_report
    assert report.gaps == ["Some evidence needed to test these explanations was not recorded; see the prerequisites of each check."]
    assert any("omitted" in item for item in report.limitations)


def test_a_sentence_gap_is_kept(monkeypatch):
    reply = json.loads(json.dumps(CAPTURED[0]["reply"]))
    reply["gaps"] = ["The fitted preprocessing for model‑1 was not recorded."]
    report = replay(CAPTURED[0], monkeypatch, reply).deep_report
    assert report.gaps == ["The fitted preprocessing for Logistic regression (lr1) was not recorded."]


def test_checks_refuted_by_recorded_warnings_fail_with_a_named_reason(monkeypatch):
    with pytest.raises(deep.DeepVerificationError) as error:
        replay(CAPTURED[2], monkeypatch)
    assert error.value.code == "premise"


def test_a_check_that_skips_the_worst_patterns_is_still_rejected(monkeypatch):
    with pytest.raises(deep.DeepVerificationError) as error:
        replay(CAPTURED[3], monkeypatch)
    assert error.value.code == "priority"


def test_gaps_are_described_to_the_provider():
    schema = deep.DeepProviderSynthesis.model_json_schema()
    assert "No paths, file names, numbers or URLs" in json.dumps(schema)
