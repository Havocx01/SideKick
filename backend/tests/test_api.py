"""The API surface in replay mode."""

from __future__ import annotations


class TestHealth:
    def test_health_states_what_the_deployment_can_do(self, client):
        payload = client.get("/api/health").json()
        assert payload["status"] == "ok"
        assert payload["mode"] == "replay"
        assert payload["can_train"] is False
        assert payload["bundle"]["available"] is True
        # The hosted demo must not imply it trains.
        assert "recorded evidence" in payload["note"]

    def test_the_root_points_at_the_documentation(self, client):
        payload = client.get("/").json()
        assert payload["docs"] == "/docs"

    def test_the_configuration_fingerprint_is_exposed(self, client):
        payload = client.get("/api/config").json()
        assert payload["config_fingerprint"]
        assert "horizon_cycles" in payload["config"]


class TestEvidenceRoutes:
    def test_profile(self, client):
        payload = client.get("/api/profile").json()
        assert payload["equipment_count"] > 0
        assert payload["data_hash"]
        assert payload["findings"]

    def test_splits_are_disjoint_over_the_wire(self, client):
        payload = client.get("/api/splits").json()
        assert not set(payload["holdout"]) & set(payload["development"])
        assert payload["seed"]

    def test_candidates_describe_themselves(self, client):
        payload = client.get("/api/candidates").json()
        assert payload
        assert all(entry["description"] for entry in payload)

    def test_selection_carries_criteria_and_ranking(self, client):
        payload = client.get("/api/selection").json()
        assert payload["outcome"] in {"qualified", "none_qualified"}
        assert payload["criteria"]["min_detection_fraction"] > 0
        assert payload["ranked"]

    def test_the_holdout_is_reported_as_unscored(self, client):
        payload = client.get("/api/final-evaluation").json()
        assert payload["available"] is False
        assert "frozen" in payload["note"] or "once" in payload["note"]

    def test_scenarios_can_be_filtered_to_the_required_set(self, client):
        everything = client.get("/api/scenarios").json()
        required = client.get("/api/scenarios?required_only=true&include_clean=false").json()
        assert len(required) < len(everything)
        assert all(entry["required"] for entry in required)

    def test_scenarios_can_be_filtered_by_candidate(self, client):
        payload = client.get("/api/scenarios?candidate=age_baseline").json()
        assert payload
        assert {entry["candidate"] for entry in payload} == {"age_baseline"}

    def test_every_scenario_result_carries_an_interval(self, client):
        for entry in client.get("/api/scenarios").json():
            interval = entry["metrics"]["detection_ci"]
            assert interval["lower"] <= entry["metrics"]["detection_fraction"] <= interval["upper"]

    def test_replay_index_lists_outcomes(self, client):
        payload = client.get("/api/replay/index").json()
        assert payload["series"]
        assert payload["equipment"]
        for entry in payload["series"]:
            assert entry["cycles"] > 0

    def test_replay_series_are_cycle_ordered(self, client):
        series = client.get("/api/replay").json()
        assert series
        for entry in series:
            cycles = [point["cycle"] for point in entry["points"]]
            assert cycles == sorted(cycles)

    def test_an_unknown_engine_returns_not_found(self, client):
        assert client.get("/api/replay?equipment_id=NOPE").status_code == 404

    def test_limitations_are_served_with_the_evidence(self, client):
        payload = client.get("/api/limitations").json()
        assert len(payload["limitations"]) >= 5
        assert any("simulated" in item for item in payload["limitations"])

    def test_runs_are_listed_and_individually_addressable(self, client):
        runs = client.get("/api/runs").json()
        assert runs
        first = runs[0]["run_id"]
        assert client.get(f"/api/runs/{first}").json()["run_id"] == first

    def test_an_unknown_run_returns_not_found(self, client):
        assert client.get("/api/runs/nope").status_code == 404


class TestCopilotRoutes:
    def test_the_tool_surface_is_published(self, client):
        payload = client.get("/api/copilot/tools").json()
        assert len(payload["tools"]) == 6
        assert "never sent to the language model" in payload["note"]

    def test_status_reports_the_absence_of_a_key(self, client):
        payload = client.get("/api/copilot/status").json()
        assert payload["available"] is False
        assert payload["language_model"] is None

    def test_a_question_is_answered_from_evidence_without_a_key(self, client):
        response = client.post("/api/copilot", json={"question": "Which model should we deploy?"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["degraded"] is True
        assert payload["unverified_claims"] == 0
        assert payload["text"]

    def test_an_empty_question_is_rejected(self, client):
        assert client.post("/api/copilot", json={"question": ""}).status_code == 422

    def test_an_unknown_field_is_rejected(self, client):
        response = client.post(
            "/api/copilot", json={"question": "hi", "sql": "DROP TABLE runs"}
        )
        assert response.status_code == 422

    def test_suggestions_are_offered(self, client):
        assert len(client.get("/api/copilot/suggestions").json()["suggestions"]) >= 5


class TestMissingBundle:
    def test_evidence_routes_explain_a_missing_bundle(self, monkeypatch, tmp_path):
        from fastapi.testclient import TestClient

        from app.api.deps import reload_bundle
        from app.config import reset_settings
        from app.main import create_app

        monkeypatch.setenv("SIDEKICK_MODE", "replay")
        monkeypatch.setenv("SIDEKICK_BUNDLE_PATH", str(tmp_path / "absent.json"))
        reset_settings()
        reload_bundle()

        with TestClient(create_app()) as client:
            response = client.get("/api/profile")
            assert response.status_code == 503
            assert "run_pipeline" in response.json()["detail"]
            # Health must stay usable so a deploy can be diagnosed.
            assert client.get("/api/health").json()["bundle"]["available"] is False

        reload_bundle()
        reset_settings()
