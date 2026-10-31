"""Offline proof of the hosted perimeter and persistent single-workspace admission."""
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import AsyncOpenAI
from pydantic import BaseModel

from app import config
from app.assistant import transport
from app.config import Settings
from app.hosted import COOKIE, HostedAccess, accessFor, hashPassword, reserveInference, reserveSearch

ORIGIN = "https://workspace.example"
HEADERS = {"origin": ORIGIN, "x-sidekick-request": "1"}
PASSWORD = "correct horse battery staple"


@pytest.fixture(scope="module")
def passwordHash():
    return hashPassword(PASSWORD)


@pytest.fixture
def hosted(tmp_path, monkeypatch, passwordHash):
    monkeypatch.setenv("SIDEKICK_STATIC_DIR", str(tmp_path / "static"))
    (tmp_path / "static").mkdir()
    (tmp_path / "static" / "index.html").write_text("<html>Sign in</html>")
    (tmp_path / "static" / "assets").mkdir()
    (tmp_path / "static" / "assets" / "app.js").write_text("console.log('shell')")
    settings = Settings(mode="full", hosted_owner="adam", hosted_origin=ORIGIN,
        hosted_password_hash=passwordHash, artifacts_dir=tmp_path / "artifacts", data_dir=tmp_path / "data",
        bundle_path=Path(__file__).resolve().parents[1] / "evidence" / "bundle.json",
        mlflow_enabled=False, nebius_api_key="", tavily_api_key="")
    monkeypatch.setattr(config, "_settings", settings)
    from app.api.deps import _cached_bundle
    _cached_bundle.cache_clear()
    from app.main import create_app
    with TestClient(create_app(), base_url=ORIGIN) as client:
        yield client, settings
    _cached_bundle.cache_clear()


def login(client):
    response = client.post("/api/session/login", headers=HEADERS, json={"username": "adam", "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response


def test_hosted_default_and_configuration_are_guarded(tmp_path, passwordHash, monkeypatch):
    monkeypatch.delenv("SIDEKICK_ASSISTANT_LIVE_ENABLED", raising=False)
    base = dict(mode="full", artifacts_dir=tmp_path, hosted_owner="adam", hosted_origin=ORIGIN, hosted_password_hash=passwordHash)
    settings = Settings(**base)
    assert settings.hosted and not settings.assistant_live_enabled
    assert settings.hosted_max_calls == settings.hosted_max_completion_tokens == settings.hosted_max_searches == 0
    assert passwordHash not in repr(settings) and PASSWORD not in passwordHash
    assert int(passwordHash.split("$")[2]) >= 600_000
    assert hashPassword(PASSWORD) != passwordHash
    for change in ({"mode": "demo"}, {"mode": "replay"}, {"hosted_origin": ""}, {"hosted_owner": ""},
            {"hosted_password_hash": "plaintext"}, {"hosted_owner": "a" * 65}, {"hosted_max_calls": -1}, {"hosted_max_mutations": 10001},
            {"hosted_max_upload_bytes": 25 * 1024 * 1024 + 1}, {"hosted_session_seconds": 28801}):
        with pytest.raises(ValueError):
            Settings(**{**base, **change})
    for origin in ("http://workspace.example", "https://user:pass@workspace.example", ORIGIN + "/", ORIGIN + "/api",
            ORIGIN + "?x=y", ORIGIN + "#fragment", "https://workspace.example:invalid", "https://workspace.example:0"):
        with pytest.raises(ValueError):
            Settings(**{**base, "hosted_origin": origin})
    assert Settings(**{**base, "hosted_origin": ORIGIN + ":443"}).hosted_origin == ORIGIN
    for password in ("short", "x" * 1025):
        with pytest.raises(ValueError):
            hashPassword(password)


@pytest.mark.parametrize("mode", ["full", "demo", "replay"])
def test_existing_modes_keep_open_session_contract(mode, tmp_path, monkeypatch):
    monkeypatch.delenv("SIDEKICK_ASSISTANT_LIVE_ENABLED", raising=False)
    settings = Settings(mode=mode, artifacts_dir=tmp_path / mode, data_dir=tmp_path / "data")
    assert settings.assistant_live_enabled
    monkeypatch.setattr(config, "_settings", settings)
    from app.main import create_app
    with TestClient(create_app()) as client:
        assert client.get("/api/session").json() == {"required": False, "authenticated": True, "owner": None, "budgets": None}


@pytest.mark.parametrize("value,enabled", [("0", False), ("1", True)])
def test_hosted_live_setting_honors_explicit_operator_environment(tmp_path, passwordHash, monkeypatch, value, enabled):
    monkeypatch.setenv("SIDEKICK_ASSISTANT_LIVE_ENABLED", value)
    settings = Settings(mode="full", artifacts_dir=tmp_path, hosted_owner="adam", hosted_origin=ORIGIN, hosted_password_hash=passwordHash)
    assert settings.assistant_live_enabled is enabled


def test_private_surface_health_login_and_logout(hosted):
    client, settings = hosted
    anonymous = {"required": True, "authenticated": False, "owner": None, "budgets": None}
    assert client.get("/api/session").json() == anonymous
    assert client.get("/api/health").json() == {"status": "ok", "requires_sign_in": True}
    assert client.get("/").status_code == client.get("/assets/app.js").status_code == 200
    for path in ("/api/library", "/api/config", "/api/investigations", "/api/not-a-route", "/docs", "/redoc", "/openapi.json", "/exports/private.json"):
        assert client.get(path).status_code == 401
    assert client.post("/api/library/folders", headers=HEADERS, json={"name": "forbidden"}).status_code == 401
    response = login(client)
    cookie = response.headers["set-cookie"]
    assert COOKIE + "=" in cookie and "Secure" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert "Path=/" in cookie and "Domain=" not in cookie and "Max-Age=28800" in cookie
    state = response.json()
    assert state["owner"] == "adam" and state["authenticated"] and state["budgets"]["mutations"] == 200
    token = client.cookies.get(COOKIE)
    raw = accessFor(settings).path.read_bytes()
    assert token.encode() not in raw and PASSWORD.encode() not in raw
    assert client.get("/docs").status_code == 200
    assert client.get("/api/health").json()["can_train"] is True
    assert client.get("/api/health").headers["cache-control"] == "no-store"
    created = client.post("/api/library/folders", headers=HEADERS, json={"name": "Persistent private folder"})
    assert created.status_code == 201, created.text
    assert client.get("/api/session").json()["budgets"]["mutations"] == 199
    assert "Persistent private folder" in client.get("/api/library").text
    assert client.post("/api/session/logout", headers=HEADERS).json() == anonymous
    assert not accessFor(settings).authenticated(token)
    assert client.get("/api/library").status_code == 401
    assert client.get("/").status_code == 200
    client.cookies.set(COOKIE, token, domain="workspace.example", path="/")
    assert client.get("/api/library").status_code == 401


@pytest.mark.parametrize("headers", [{}, {"origin": ORIGIN}, {"x-sidekick-request": "1"},
    {**HEADERS, "origin": "https://evil.example"}, {**HEADERS, "origin": "null"}])
def test_csrf_is_required_for_login_and_private_mutations(hosted, headers):
    client, _ = hosted
    assert client.post("/api/session/login", headers=headers, json={"username": "adam", "password": PASSWORD}).status_code == 400
    login(client)
    assert client.post("/api/library/folders", headers=headers, json={"name": "No"}).status_code == 400
    assert client.post("/api/session/logout", headers=headers).status_code == 400


def test_anonymous_mutations_outside_api_never_read_the_body(hosted):
    client, _ = hosted
    chunks = []
    def body():
        chunks.append("read")
        yield b"x" * 10000
    for path in ("/", "/assets/app.js", "/anything", "/api/library/folders"):
        assert client.post(path, headers=HEADERS, content=body()).status_code == 401
    assert chunks == []


def test_host_tls_and_forwarded_header_spoofing_are_rejected(hosted):
    client, _ = hosted
    assert client.get("/api/session", headers={"host": "evil.example"}).status_code == 400
    assert client.get("http://workspace.example/api/session", headers={"x-forwarded-proto": "https"}).status_code == 400
    assert client.post("http://workspace.example/api/session/login", headers={**HEADERS, "x-forwarded-proto": "https"}, json={}).status_code == 400
    assert client.get("http://workspace.example/api/health").json() == {"status": "ok", "requires_sign_in": True}
    login(client)
    assert client.get("/api/library", headers={"host": "evil.example", "x-forwarded-host": "workspace.example"}).status_code == 400


def test_body_limits_apply_to_streamed_requests_before_processing(hosted):
    client, settings = hosted
    assert client.post("/api/session/login", headers=HEADERS, content=iter([b"x" * 4000, b"x" * 5000])).status_code == 413
    assert client.post("/api/session/login", headers=HEADERS, content=b"x",).status_code == 400
    assert client.post("/api/session/login", headers=HEADERS, json=[]).status_code == 400
    login(client)
    settings.hosted_max_upload_bytes = 20
    assert client.post("/api/library/folders", headers=HEADERS, content=iter([b"x" * 10, b"x" * 11])).status_code == 413
    assert client.post("/api/library/folders", headers={**HEADERS, "content-length": "999"}, content=b"{}").status_code == 413
    assert client.get("/api/session").json()["budgets"]["mutations"] == 200


def test_login_limit_is_global_durable_and_credentials_do_not_enumerate(hosted):
    client, settings = hosted
    # Use wrong usernames and wrong passwords to prove a single shared limit.
    for index in range(20):
        response = client.post("/api/session/login", headers=HEADERS,
            json={"username": "adam" if index % 2 else "unknown", "password": "incorrect password"})
        assert response.status_code == 401
    restarted = HostedAccess(replace(settings))
    assert restarted.login("adam", PASSWORD)[1] == 429
    assert client.post("/api/session/login", headers=HEADERS, json={"username": "adam", "password": PASSWORD}).status_code == 429


def test_session_expiry_rotation_logout_and_workspace_owner_binding(hosted):
    client, settings = hosted
    login(client)
    token = client.cookies.get(COOKIE)
    reopened = HostedAccess(replace(settings))
    assert reopened.authenticated(token)
    with reopened.transaction() as db:
        db.execute("UPDATE sessions SET expires=0")
    assert client.get("/api/session").json()["authenticated"] is False
    assert client.get("/api/library").status_code == 401
    assert client.post("/api/session/logout", headers=HEADERS).status_code == 200
    with reopened.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    login(client)
    token = client.cookies.get(COOKIE)
    rotated = HostedAccess(replace(settings, hosted_password_hash=hashPassword("a new strong password")))
    assert not rotated.authenticated(token) and not reopened.authenticated(token)
    assert reopened.login("adam", PASSWORD)[1] == 401
    other = HostedAccess(replace(settings, hosted_owner="bob", artifacts_dir=settings.artifacts_dir.parent / "bob"))
    assert not other.authenticated(token)
    with pytest.raises(ValueError, match="different hosted owner"):
        HostedAccess(replace(settings, hosted_owner="bob"))


def test_owner_binding_precedes_job_recovery(hosted, monkeypatch):
    _, settings = hosted
    monkeypatch.setattr(config, "_settings", replace(settings, hosted_owner="bob"))
    from app.main import create_app
    from app.experiments import jobs
    monkeypatch.setattr(jobs, "Jobs", lambda *_: pytest.fail("Owner binding must precede worker recovery"))
    with pytest.raises(ValueError, match="different hosted owner"):
        with TestClient(create_app(), base_url=ORIGIN):
            pass


def test_two_deployments_have_separate_artifacts_and_sessions(hosted, monkeypatch):
    client, settings = hosted
    login(client)
    cookie = client.cookies.get(COOKIE)
    assert client.post("/api/library/folders", headers=HEADERS, json={"name": "Adam private"}).status_code == 201
    otherSettings = replace(settings, hosted_owner="bob", artifacts_dir=settings.artifacts_dir.parent / "bob")
    monkeypatch.setattr(config, "_settings", otherSettings)
    from app.main import create_app
    with TestClient(create_app(), base_url=ORIGIN) as other:
        other.cookies.set(COOKIE, cookie, domain="workspace.example", path="/")
        assert other.get("/api/library").status_code == 401
        assert other.post("/api/session/login", headers=HEADERS, json={"username": "bob", "password": PASSWORD}).status_code == 200
        assert "Adam private" not in other.get("/api/library").text
    monkeypatch.setattr(config, "_settings", settings)
    assert "Adam private" in client.get("/api/library").text


def test_daily_mutation_quota_precedes_work_and_survives_session_changes(hosted):
    client, settings = hosted
    settings.hosted_max_mutations = 1
    login(client)
    assert client.post("/api/library/folders", headers=HEADERS, json={"name": "One"}).status_code == 201
    assert client.post("/api/library/folders", headers=HEADERS, json={"name": "Two"}).status_code == 429
    assert "Two" not in client.get("/api/library").text
    client.post("/api/session/logout", headers=HEADERS)
    login(client)
    assert client.post("/api/library/folders", headers=HEADERS, json={"name": "Three"}).status_code == 429
    assert HostedAccess(replace(settings)).budgets()["mutations"] == 0


def test_budget_reservations_are_atomic_durable_and_day_bound(hosted):
    _, settings = hosted
    settings.hosted_max_calls = 7
    settings.hosted_max_completion_tokens = 70
    settings.hosted_max_searches = 2
    access = accessFor(settings)
    def reserve(_):
        try:
            reserveInference(settings, 10)
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=16) as pool:
        assert sum(pool.map(reserve, range(50))) == 7
    reserveSearch(settings)
    reserveSearch(settings)
    with pytest.raises(ValueError):
        reserveSearch(settings)
    reopened = HostedAccess(replace(settings))
    assert reopened.budgets() == {"calls": 0, "completionTokens": 0, "searches": 0, "mutations": 200}
    with pytest.raises(ValueError):
        reopened.reserve(calls=1, tokens=1)
    with access.connection() as db:
        db.execute("UPDATE usage SET day='2000-01-01'")
    assert access.budgets()["calls"] == 7
    reserveInference(settings, 10)
    assert access.budgets()["calls"] == 6


class Answer(BaseModel):
    text: str


@pytest.mark.parametrize("method", ["structured", "tools"])
@pytest.mark.parametrize("failed", [False, True])
def test_both_transports_reserve_exact_total_tokens_and_never_retry(hosted, method, failed):
    _, settings = hosted
    settings.nebius_reasoning_tokens = 17
    settings.hosted_max_calls = 1
    settings.hosted_max_completion_tokens = 117
    requests = []
    def respond(request):
        requests.append(json.loads(request.content))
        if failed:
            return httpx.Response(503, json={"error": {"message": "Offline fixture unavailable"}})
        message = {"role": "assistant", "content": '{"text":"safe"}'}
        return httpx.Response(200, json={"id": "fixture", "object": "chat.completion", "created": 0,
            "model": "fixture", "choices": [{"index": 0, "finish_reason": "stop", "message": message}]})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            async with AsyncOpenAI(api_key="offline-mock", base_url=settings.nebius_base_url, max_retries=0, http_client=http) as client:
                async def invoke():
                    common = dict(history=[{"role": "user", "content": "fixture"}], max_output_tokens=100)
                    if method == "structured":
                        return await transport.request_structured(client, settings, response_model=Answer, **common)
                    return await transport.request_tool_calls(client, settings, tools=[], forced=None, **common)
                if failed:
                    from openai import APIStatusError
                    with pytest.raises(APIStatusError):
                        await invoke()
                else:
                    await invoke()
                with pytest.raises(ValueError, match="allowance"):
                    await invoke()
    asyncio.run(run())
    assert len(requests) == 1 and requests[0]["max_tokens"] == 117
    assert HostedAccess(replace(settings)).budgets()["calls"] == 0
    assert accessFor(settings).budgets()["completionTokens"] == 0


@pytest.mark.parametrize("method", ["structured", "tools"])
def test_zero_allowance_never_reaches_provider(hosted, method):
    _, settings = hosted
    def forbidden(_request):
        pytest.fail("Zero hosted allowance must never contact a provider")
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as http:
            async with AsyncOpenAI(api_key="offline", http_client=http) as client:
                with pytest.raises(ValueError, match="allowance"):
                    if method == "structured":
                        await transport.request_structured(client, settings, history=[], response_model=Answer, max_output_tokens=100)
                    else:
                        await transport.request_tool_calls(client, settings, history=[], tools=[], forced=None, max_output_tokens=100)
    asyncio.run(run())


def test_research_reserves_search_globally_before_offline_transport(hosted, monkeypatch):
    _, settings = hosted
    from app.investigator import research
    from types import SimpleNamespace
    # Exercise actual admission ordering without fitting a model or contacting a provider.
    class Store:
        def __init__(self):
            self.path = settings.artifacts_dir / "research-fixture.sqlite3"
            import sqlite3
            with sqlite3.connect(self.path) as db:
                db.execute("CREATE TABLE fault_research(investigation TEXT,attempt TEXT,status TEXT,payload TEXT)")
        def connection(self):
            import sqlite3
            return sqlite3.connect(self.path)
        def transaction(self):
            return self.connection()
        def result(self, _):
            return SimpleNamespace(scenario=SimpleNamespace(components=[]))
    fixture = Store()
    calls = []
    async def offline(client, key, query):
        calls.append(query)
        if len(calls) == 2:
            raise httpx.ConnectError("offline transport failure")
        return {"results": []}
    monkeypatch.setattr(research, "search", offline)
    async def run():
        first = await research.runResearch(fixture, "investigation", "zero", settings, lambda: True)
        assert first.status == "failed" and first.searchRequests == 0
        settings.hosted_max_searches = 1
        second = await research.runResearch(fixture, "investigation", "one", settings, lambda: True)
        assert second.status == "completed" and second.searchRequests == 1
        third = await research.runResearch(fixture, "investigation", "two", replace(settings), lambda: True)
        assert third.status == "failed" and third.searchRequests == 0
        settings.hosted_max_searches = 2
        failed = await research.runResearch(fixture, "investigation", "failed", settings, lambda: True)
        assert failed.status == "failed" and failed.searchRequests == 1
        blocked = await research.runResearch(fixture, "investigation", "blocked", settings, lambda: True)
        assert blocked.status == "failed" and blocked.searchRequests == 0
    asyncio.run(run())
    assert len(calls) == 2 and HostedAccess(replace(settings)).budgets()["searches"] == 0


def test_restarted_app_retains_artifacts_sessions_and_counters(tmp_path, monkeypatch, passwordHash):
    settings = Settings(mode="full", hosted_owner="adam", hosted_origin=ORIGIN, hosted_password_hash=passwordHash,
        artifacts_dir=tmp_path / "artifacts", data_dir=tmp_path / "data", mlflow_enabled=False,
        nebius_api_key="", tavily_api_key="")
    monkeypatch.setattr(config, "_settings", settings)
    from app.main import create_app
    with TestClient(create_app(), base_url=ORIGIN) as client:
        login(client)
        cookie = client.cookies.get(COOKIE)
        assert client.post("/api/library/folders", headers=HEADERS, json={"name": "Saved across restart"}).status_code == 201
    monkeypatch.setattr(config, "_settings", replace(settings))
    with TestClient(create_app(), base_url=ORIGIN) as client:
        client.cookies.set(COOKIE, cookie, domain="workspace.example", path="/")
        assert client.get("/api/session").json()["authenticated"]
        assert client.get("/api/session").json()["budgets"]["mutations"] == 199
        assert "Saved across restart" in client.get("/api/library").text


def test_interrupted_inference_keeps_its_reservation(hosted):
    _, settings = hosted
    settings.hosted_max_calls = 1
    settings.hosted_max_completion_tokens = 5000
    async def interrupted(**_):
        raise asyncio.CancelledError
    from types import SimpleNamespace
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=interrupted)))
    async def run():
        with pytest.raises(asyncio.CancelledError):
            await transport.request_structured(client, settings, history=[], response_model=Answer, max_output_tokens=100)
        with pytest.raises(ValueError, match="allowance"):
            await transport.request_tool_calls(client, settings, history=[], tools=[], forced=None, max_output_tokens=100)
    asyncio.run(run())
    assert HostedAccess(replace(settings)).budgets()["completionTokens"] == 804
