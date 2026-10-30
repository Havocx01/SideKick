import asyncio
import json
import threading

import httpx
import pytest

from app.investigator import research
from test_compound_faults import fitted as fitted  # noqa: F401
from test_investigations_api import HEADERS, api as api, create  # noqa: F401


def mocks(monkeypatch, *, sources=True, badCitation=False, afterSearch=None, afterSummary=None):
    calls = []
    async def search(client, key, query):
        calls.append(("tavily", query))
        if afterSearch:
            afterSearch()
        return {"results": [{"title": "Sensor manual", "url": "https://example.com/manual", "content": "Check sensor wiring."}] if sources else [], "usage": {"credits": 1}}
    async def summarize(settings, packet, meta):
        calls.append(("nemotron", packet))
        meta.update(requestId="mock-request", usage={"completion_tokens": 80})
        if afterSummary:
            afterSummary()
        return research.ResearchNote(summary="Check the signal path before assuming an equipment fault.", sourceIds=["unknown" if badCitation else "source-1"],
            tests=[research.ResearchTest(action="Inspect wiring in a supervised test.", reason="A signal-path fault can affect readings.", sourceIds=["source-1"])])
    monkeypatch.setattr(research, "search", search)
    monkeypatch.setattr(research, "summarize", summarize)
    return calls


def finished(api):
    client, service, root = api
    service.settings.tavily_api_key = "mock-tavily"
    investigation = create(client, seed=0)
    response = client.post(f"/api/investigations/{investigation}/start", headers=HEADERS, json={"requestId": "prepare-research"})
    assert response.status_code == 200
    service.wait(investigation)
    attempts = service.store.load(investigation).attempts
    assert len(attempts) == 1 and attempts[0].status == "completed"
    return client, service, root, investigation, attempts[0].id


def start(client, investigation, attempt, requestId="research-request", allowResearch=True):
    return client.post(f"/api/investigations/{investigation}/research", headers=HEADERS,
        json={"requestId": requestId, "attempt": attempt, "allowResearch": allowResearch})


def test_research_saves_sources_and_reuses_them_without_loading_a_context(api, monkeypatch):
    client, service, root, investigation, attempt = finished(api)
    calls = mocks(monkeypatch)
    before = service.store.result(attempt).model_dump(mode="json")
    monkeypatch.setattr(service, "evaluator", lambda _: pytest.fail("Research must not load a fitted context"))
    assert start(client, investigation, attempt).status_code == 200
    service.wait(investigation)
    saved = client.get(f"/api/investigations/{investigation}", headers=HEADERS).json()["research"][0]
    assert saved["status"] == "completed" and saved["note"]["sourceIds"] == ["source-1"]
    assert saved["sources"][0]["url"] == "https://example.com/manual"
    assert saved["searchRequests"] == saved["modelRequests"] == 1 and saved["reportedCompletionTokens"] == 80
    assert "oil_particles" not in json.dumps(calls) and "equipment_id" not in json.dumps(calls)
    assert start(client, investigation, attempt, "another-request").status_code == 200
    service.wait(investigation)
    assert [name for name, _ in calls] == ["tavily", "nemotron"]
    assert service.store.result(attempt).model_dump(mode="json") == before
    assert "research" not in client.get(f"/api/investigations/{investigation}/public-export", headers=HEADERS).json()


def test_research_checks_owner_attempt_consent_and_keys_before_any_calls(api, monkeypatch):
    client, service, root, investigation, attempt = finished(api)
    calls = mocks(monkeypatch)
    body = {"requestId": "research-request", "attempt": attempt, "allowResearch": True}
    path = f"/api/investigations/{investigation}/research"
    assert client.post(path, headers={"x-owner": "bob"}, json=body).status_code == 404
    assert start(client, investigation, "missing").status_code == 404
    assert start(client, create(client, seed=0), attempt).status_code == 404
    assert start(client, investigation, attempt, allowResearch=False).status_code == 403
    client.app.state.assistant.allowed = False
    assert start(client, investigation, attempt).status_code == 403
    client.app.state.assistant.allowed = True
    service.settings.tavily_api_key = ""
    assert start(client, investigation, attempt).status_code == 422
    assert calls == []


@pytest.mark.parametrize("outcome", ["revoked", "cancelled", "badCitation", "empty", "lateRevocation", "restart"])
def test_research_does_not_publish_unsupported_or_cancelled_advice(api, monkeypatch, outcome):
    client, service, root, investigation, attempt = finished(api)
    def afterSearch():
        if outcome == "revoked":
            client.app.state.assistant.allowed = False
        if outcome == "cancelled":
            service.cancel("alice", investigation)
    def afterSummary():
        if outcome == "lateRevocation":
            client.app.state.assistant.allowed = False
        if outcome == "restart":
            from app.investigator.service import InvestigationService
            reopened = InvestigationService(root, service.settings)
            reopened.close()
    calls = mocks(monkeypatch, sources=outcome != "empty", badCitation=outcome == "badCitation", afterSearch=afterSearch, afterSummary=afterSummary)
    assert start(client, investigation, attempt).status_code == 200
    service.wait(investigation)
    saved = client.get(f"/api/investigations/{investigation}", headers=HEADERS).json()["research"][0]
    expected = {"badCitation": "failed", "empty": "completed", "restart": "interrupted"}.get(outcome, "cancelled")
    assert saved["status"] == expected and saved["note"] is None
    assert len(calls) == (2 if outcome in {"badCitation", "lateRevocation", "restart"} else 1)
    assert saved["sources"] == []
    if outcome in {"lateRevocation", "restart"}:
        assert saved["reportedCompletionTokens"] == 80


def test_search_failure_is_saved_without_retry_or_a_model_request(api, monkeypatch):
    client, service, root, investigation, attempt = finished(api)
    calls = mocks(monkeypatch)
    async def unavailable(*_):
        calls.append(("tavily", "failed"))
        raise httpx.ConnectError("unavailable")
    monkeypatch.setattr(research, "search", unavailable)
    start(client, investigation, attempt)
    service.wait(investigation)
    report = service.view("alice", investigation).research[0]
    assert report.status == "failed" and report.searchRequests == 1 and report.modelRequests == 0
    start(client, investigation, attempt, "different-request")
    service.wait(investigation)
    assert len(calls) == 1


def test_pending_research_is_not_started_twice(api, monkeypatch):
    client, service, root, investigation, attempt = finished(api)
    entered, release = threading.Event(), threading.Event()
    def wait():
        entered.set()
        assert release.wait(10)
    calls = mocks(monkeypatch, afterSearch=wait)
    try:
        start(client, investigation, attempt)
        assert entered.wait(10)
        assert start(client, investigation, attempt, "duplicate-request").status_code == 200
    finally:
        release.set()
        service.wait(investigation)
    assert len(calls) == 2


def test_tavily_transport_is_bounded_and_does_not_send_private_context():
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"results": [], "usage": {"credits": 1}})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await research.search(client, "mock-key", "industrial sensor stuck readings")
    assert asyncio.run(run())["results"] == []
    assert len(requests) == 1 and str(requests[0].url) == "https://api.tavily.com/search"
    assert requests[0].headers["authorization"] == "Bearer mock-key"
    body = json.loads(requests[0].content)
    assert body["max_results"] == 3 and body["search_depth"] == "basic" and not body["include_raw_content"]


def test_source_links_are_safe_bounded_and_deduplicated():
    rows = [{"url": url, "title": "Sensor manual", "content": "x" * 3000} for url in
        ("javascript:alert(1)", "https://user:password@example.com", "https://example.com/manual", "https://example.com/manual")]
    sources = research.sourcesFrom({"results": rows})
    assert len(sources) == 1 and len(sources[0].content) <= 1500


def test_unrelated_search_results_are_not_used_as_sensor_references():
    rows = [{"title": "Microsoft account", "url": "https://account.microsoft.com", "content": "Sign in to manage your account."}]
    assert research.sourcesFrom({"results": rows}) == []
    note = research.ResearchNote(summary="No supported sensor test can be derived.", sourceIds=["source-1"], tests=[])
    assert note.tests == []
