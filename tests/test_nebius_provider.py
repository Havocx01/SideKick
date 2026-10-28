"""Nebius contracts exercise real SDK serialization with no external requests."""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Literal

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import AsyncOpenAI, AuthenticationError

from app.config import Settings
from app.schemas import Strict
from test_deep_investigation import BODY, HEADERS, checked_fixture, completed, deep_app as deep_app, fake_provider, provider_synthesis


class Probe(Strict):
    status: Literal["ok"]
    count: int


def configured(**overrides):
    return Settings(assistant_provider="nebius", nebius_api_key="nebius-test-secret", **overrides)


def completion(content=None, *, calls=None, finish="stop", refusal=None):
    return {"id": "chatcmpl-test", "object": "chat.completion", "created": 0, "model": "fixture",
        "choices": [{"index": 0, "finish_reason": finish,
            "message": {"role": "assistant", "content": content, "tool_calls": calls, "refusal": refusal}}]}


def test_nebius_configuration_uses_its_own_key_and_provider_model(monkeypatch):
    from app.assistant.transport import api_key, client_options
    monkeypatch.delenv("SIDEKICK_ASSISTANT_MODEL", raising=False)
    settings = configured(openai_api_key="different-openai-secret")
    assert settings.assistant_model == "nvidia/nemotron-3-super-120b-a12b"
    options = client_options(settings)
    assert options["api_key"] == "nebius-test-secret" and options["max_retries"] == 0
    assert options["base_url"] == "https://api.tokenfactory.nebius.com/v1/"
    settings.nebius_api_key = ""
    assert not api_key(settings)  # Never silently send the OpenAI credential to Nebius.
    assert "nebius-test-secret" not in repr(settings)


@pytest.mark.parametrize("endpoint", ["http://api.tokenfactory.nebius.com/v1/", "https://attacker.invalid/v1/",
    "https://api.tokenfactory.nebius.com.attacker.invalid/v1/", "https://user:secret@api.tokenfactory.nebius.com/v1/",
    "https://api.tokenfactory.nebius.com/v1/?key=secret"])
def test_nebius_rejects_unsafe_or_unrelated_endpoints(endpoint):
    with pytest.raises(ValueError, match="Nebius endpoint"):
        configured(nebius_base_url=endpoint)


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError, match="SIDEKICK_ASSISTANT_PROVIDER"):
        Settings(assistant_provider="unknown")


def test_default_probe_is_offline_and_missing_key_never_falls_back_to_openai():
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "NEBIUS_API_KEY": "", "OPENAI_API_KEY": "mock-openai-do-not-use",
        "SIDEKICK_ASSISTANT_PROVIDER": "openai", "SIDEKICK_ASSISTANT_MODEL": "gpt-4.1-mini-2025-04-14",
        "SIDEKICK_NEBIUS_BASE_URL": "https://api.tokenfactory.nebius.com/v1/"}
    command = [sys.executable, str(root / "scripts/check_nebius.py")]
    offline = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=15)
    assert offline.returncode == 0
    report = json.loads(offline.stdout)
    assert report["model"].startswith("nvidia/") and not report["credential_configured"] and not report["live_verified"]
    live = subprocess.run([*command, "--live"], cwd=root, env=env, capture_output=True, text=True, timeout=15)
    assert live.returncode == 2 and "NEBIUS_API_KEY" in live.stdout
    assert "mock-openai-do-not-use" not in offline.stdout + live.stdout


def test_structured_chat_uses_schema_and_local_validation():
    from app.assistant.transport import request_structured
    requests = []
    def respond(request):
        requests.append(json.loads(request.content))
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(200, json=completion('{"status":"ok","count":2}'))
    async def run():
        async with AsyncOpenAI(api_key="mock", base_url="http://fixture.invalid/v1/",
                http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))) as client:
            return await request_structured(client, configured(), history=[{"role": "user", "content": "Synthetic check"}],
                response_model=Probe, max_output_tokens=128)
    result = asyncio.run(run())
    assert result.status == "ok" and result.count == 2
    payload = requests[0]
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert payload["max_tokens"] == 128 and "input" not in payload and "store" not in payload


@pytest.mark.parametrize("content,finish,refusal", [
    ('{"status":"ok","count":2}', "length", None),
    ('{"status":"ok","count":2}', "content_filter", None),
    ('{"status":"ok","count":2}', "stop", "refused"),
    ('{"status":"invented","count":2}', "stop", None),
    ('{"status":"ok","count":"2"}', "stop", None),
    ('{"status":"ok","count":2,"extra":"untrusted"}', "stop", None),
    ("not json", "stop", None), (None, "stop", None),
])
def test_incomplete_refused_or_invalid_chat_fails_without_retry(content, finish, refusal):
    from app.assistant.transport import request_structured
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=completion(content, finish=finish, refusal=refusal))
    async def run():
        async with AsyncOpenAI(api_key="mock", max_retries=0, base_url="http://fixture.invalid/v1/",
                http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))) as client:
            return await request_structured(client, configured(), history=[], response_model=Probe, max_output_tokens=128)
    with pytest.raises(ValueError):
        asyncio.run(run())
    assert len(calls) == 1


def test_tool_calls_translate_and_replay_as_chat_messages():
    from app.assistant.transport import request_structured, request_tool_calls
    requests = []
    spec = {"type": "function", "name": "inspect", "description": "Inspect synthetic evidence",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}, "strict": True}
    def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 1:
            assert payload["tools"][0]["function"]["name"] == "inspect"
            assert payload["tool_choice"] == {"type": "function", "function": {"name": "inspect"}}
            assert payload["parallel_tool_calls"] is False
            return httpx.Response(200, json=completion(calls=[{
                "id": "call-test", "type": "function", "function": {"name": "inspect", "arguments": "{}"}}], finish="tool_calls"))
        messages = payload["messages"]
        assert messages[-2]["role"] == "assistant" and messages[-2]["tool_calls"][0]["id"] == "call-test"
        assert messages[-1] == {"role": "tool", "tool_call_id": "call-test", "content": '{"count":2}'}
        return httpx.Response(200, json=completion('{"status":"ok","count":2}'))
    async def run():
        async with AsyncOpenAI(api_key="mock", base_url="http://fixture.invalid/v1/",
                http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))) as client:
            history = [{"role": "user", "content": "Inspect"}]
            calls = await request_tool_calls(client, configured(), history=history, tools=[spec], forced="inspect", max_output_tokens=128)
            assert calls[0].name == "inspect" and calls[0].arguments == "{}"
            history.extend([calls[0].model_dump(exclude_none=True),
                {"type": "function_call_output", "call_id": "call-test", "output": '{"count":2}'}])
            return await request_structured(client, configured(), history=history, response_model=Probe, max_output_tokens=128)
    assert asyncio.run(run()).count == 2 and len(requests) == 2


@pytest.mark.parametrize("failure", [None, "citation", "truncated"])
def test_nebius_deep_workflow_uses_existing_verification_and_provider_consent(deep_app, monkeypatch, failure):
    from app.assistant import deep
    app, _ = deep_app
    settings = app.state.assistant.settings
    settings.assistant_provider = "nebius"
    settings.nebius_api_key = "mock-nebius-only"
    settings.nebius_base_url = "https://api.tokenfactory.nebius.com/v1/"
    settings.assistant_timeout_seconds = 10
    settings.openai_api_key = ""  # Availability must use the selected provider.
    app.state.assistant.store.set_workspace_consent(True)  # Old OpenAI approval is insufficient.
    requests = []
    def respond(request):
        assert request.headers["authorization"] == "Bearer mock-nebius-only"
        payload = json.loads(request.content)
        requests.append(payload)
        packet = json.loads(payload["messages"][-1]["content"])
        ids = [row["id"] for row in packet["observations"]]
        schema = payload["response_format"]["json_schema"]["schema"]
        support_ids = [row["observation_id"] for section in packet["supporting_evidence"].values() for row in section.get("items", [])]
        for field in ("hypotheses", "next_tests"):
            ref = schema["properties"][field]["items"]["$ref"].split("/")[-1]
            assert schema["$defs"][ref]["properties"]["observation_ids"]["items"]["enum"] == ids + support_ids
        output = checked_fixture(provider_synthesis(ids), packet)
        if failure == "citation":
            output["next_tests"][0]["observation_ids"] = ["private-unknown-pattern"]
        return httpx.Response(200, json=completion(json.dumps(output), finish="length" if failure == "truncated" else "stop"))
    def offline_client(**kwargs):
        assert kwargs["base_url"] == settings.nebius_base_url and kwargs["max_retries"] == 0
        return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(deep, "AsyncOpenAI", offline_client)
    with TestClient(app) as client:
        assert client.get("/api/assistant/capabilities").json()["deep_available"] is True
        state = client.get("/api/assistant/consent/workspace").json()
        assert state["allowed"] is False and "Nebius Token Factory" in state["disclosure"]
        assert "OpenAI may retain" not in state["disclosure"]
        assert client.post("/api/assistant/analyses", json=BODY, headers=HEADERS).status_code == 403
        assert requests == []
        assert client.post("/api/assistant/consent/workspace", json={"allowed": True}, headers=HEADERS).status_code == 200
        start = client.post("/api/assistant/analyses", json=BODY, headers=HEADERS).json()
        record = completed(client, start["id"])
        if failure:
            assert record["result"]["mode"] == "evidence" and record["result"]["fallback_reason"]
            assert "private-unknown-pattern" not in json.dumps(record)
        else:
            assert record["result"]["mode"] == "ai", record["result"]["fallback_reason"]
            assert record["result"]["deep_report"]["next_tests"]
        routine = client.post("/api/assistant/analyses", json={**BODY, "task": "investigate"}, headers=HEADERS).json()
        assert routine["result"]["mode"] == "evidence"
        assert len(requests) == 1
        settings.nebius_base_url = "https://api.tokenfactory.us-central1.nebius.com/v1/"
        assert client.post("/api/assistant/analyses", json=BODY, headers=HEADERS).status_code == 403
        assert len(requests) == 1


def test_nebius_consent_survives_restart_and_revocation_clears_all_provider_approvals(deep_app):
    from app.assistant.service import AssistantService
    app, _ = deep_app
    settings = app.state.assistant.settings
    settings.assistant_provider = "nebius"
    settings.nebius_base_url = "https://api.tokenfactory.nebius.com/v1/"
    first = app.state.assistant
    assert first.workspace_consent() is False
    first.allow_workspace()
    restarted = AssistantService(settings)
    assert restarted.workspace_consent() is True
    asyncio.run(restarted.revoke_workspace())
    assert AssistantService(settings).workspace_consent() is False
    settings.assistant_provider = "openai"
    assert AssistantService(settings).workspace_consent() is False


def test_nebius_approval_does_not_authorize_an_openai_request(deep_app):
    app, _ = deep_app
    assistant = app.state.assistant
    assistant.settings.assistant_provider = "nebius"
    assistant.settings.nebius_base_url = "https://api.tokenfactory.nebius.com/v1/"
    assistant.allow_workspace()
    assert assistant.workspace_consent() is True
    assistant.settings.assistant_provider = "openai"
    assert not assistant.workspace_consent()
    assert assistant.live_reason("owner", None, False) == "Enable AI analysis for this workspace."


def test_existing_report_stays_readable_when_new_provider_or_endpoint_is_not_approved(deep_app, monkeypatch):
    app, _ = deep_app
    calls = fake_provider(monkeypatch)
    assistant = app.state.assistant
    assistant.store.set_workspace_consent(True)
    with TestClient(app) as client:
        start = client.post("/api/assistant/analyses", json=BODY, headers=HEADERS).json()
        record = completed(client, start["id"])
        assert record["result"]["mode"] == "ai"
        assistant.settings.assistant_provider = "nebius"
        assistant.settings.nebius_api_key = "mock-nebius"
        for endpoint in ("https://api.tokenfactory.nebius.com/v1/", "https://api.tokenfactory.us-central1.nebius.com/v1/"):
            assistant.settings.nebius_base_url = endpoint
            saved = client.get(f"/api/assistant/analyses/{record['id']}").json()
            assert saved["result"]["mode"] == "ai" and saved["result"]["deep_report"]
            assert saved["output_currency"] == "historical"
            reused = client.post("/api/assistant/analyses?reuse=true", json=BODY, headers=HEADERS).json()
            assert reused["id"] == record["id"] and reused["result"]["deep_report"]
            assert client.post("/api/assistant/analyses", json=BODY, headers=HEADERS).status_code == 403
        assert len(calls) == 1
        client.post("/api/assistant/consent/workspace", json={"allowed": False}, headers=HEADERS)
        revoked = client.get(f"/api/assistant/analyses/{record['id']}").json()
        assert revoked["result"]["mode"] == "evidence"
def test_nebius_failures_are_actionable_and_sanitized():
    from app.assistant.service import provider_failure
    response = httpx.Response(401, request=httpx.Request("POST", "https://api.tokenfactory.nebius.com/v1/chat/completions"))
    error = AuthenticationError("private-provider-text secret", response=response, body={})
    message = provider_failure(error, configured())
    assert "Nebius" in message and "NEBIUS_API_KEY" in message
    assert "private-provider-text" not in message and "nebius-test-secret" not in message


def test_provider_and_endpoint_change_live_identity_without_changing_evidence_identity(deep_app):
    from app.assistant.schemas import AnalysisRequest
    app, loaded = deep_app
    assistant = app.state.assistant
    context = AnalysisRequest.model_validate(BODY)
    live_before = assistant.identities(loaded, context, True)[0]
    local_before = assistant.identities(loaded, context, False)[0]
    assistant.settings.assistant_provider = "nebius"
    assistant.settings.nebius_base_url = "https://api.tokenfactory.nebius.com/v1/"
    live_after = assistant.identities(loaded, context, True)[0]
    assert live_after != live_before
    assert assistant.identities(loaded, context, False)[0] == local_before
    assistant.settings.nebius_base_url = "https://api.tokenfactory.us-central1.nebius.com/v1/"
    assert assistant.identities(loaded, context, True)[0] != live_after
