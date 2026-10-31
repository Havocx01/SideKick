import json

from app.faults.evaluator import FixedDevelopmentEvaluator
from app.faults.investigation import ExperimentRunner, InvestigationBudget, InvestigationStore
from app.faults.profiles import loadPolicy
from app.faults.scenarios import FaultCase
from app.investigator.findings import FindingCriterion, classify, saveCriterion, summarize
from app.investigator.search import seedSuite
from test_compound_faults import component, evaluator, fitted as fitted  # noqa: F401
from test_nemotron_controller import provider, proposal, run, setup, stop

LR = "logistic_regression/lr-probe"


def hypothesis(*refs):
    return {"suspected": "Losing this channel hides the late trend.", "supportIf": "Faulted detection falls on matched histories.",
        "weakenIf": "Detection is unchanged with full coverage.", "basedOn": list(refs)}


def withHypothesis(sensor, *refs, **changes):
    decision = proposal(sensor, **changes)
    decision["proposal"]["hypothesis"] = hypothesis(*refs)
    return decision


def payloads(store, investigation):
    with store.connection() as db:
        return [json.loads(row[0]) for row in db.execute("SELECT payload FROM proposals WHERE investigation=? ORDER BY seq", (investigation,))]


def test_hypotheses_link_to_real_results_and_unknown_refs_are_rejected(fitted, tmp_path, monkeypatch):
    fixed, store, investigation, config = setup(fitted, tmp_path)

    def decide(packet, count):
        if count == 1:
            return withHypothesis("channel-1")
        if count == 2:
            assert packet["experiments"][0]["ref"] == "result-1"
            return withHypothesis("channel-2", "result-9")
        if count == 3:
            assert packet["rejected"]["count"] == 0 and packet["recentCalls"][-1]["error"] == "invalid_proposal"
            assert packet["recentCalls"][-1]["feedback"] == "Unknown result reference result-9; basedOn may cite only result-1"
            return withHypothesis("channel-2", "result-1 (no effect at onset 20)")
        return stop()

    provider(monkeypatch, decide)
    report = run(store, fixed, config, investigation)
    assert report["experimentsUsed"] == 2 and report["callsUsed"] == 4
    saved = payloads(store, investigation)
    firstAttempt = store.load(investigation).attempts[0].id
    assert saved[0]["hypothesis"]["basedOn"] == [] and saved[1]["hypothesis"]["basedOn"] == [firstAttempt]
    assert saved[1]["hypothesis"]["weakenIf"].startswith("Detection is unchanged")


def test_packet_starts_from_clean_performance_and_summarizes_without_growing(fitted, tmp_path, monkeypatch):
    fixed, store, investigation, config = setup(fitted, tmp_path, experiments=16)
    saveCriterion(store, investigation, FindingCriterion(candidate=LR))
    onsets = iter(range(20, 60, 2))
    packets = []

    def decide(packet, count):
        packets.append(packet)
        return proposal("channel-1", onset_before_failure=next(onsets)) if count <= 14 else stop()

    provider(monkeypatch, decide)
    run(store, fixed, config, investigation, maxCalls=15, maxCompletionTokens=100000)
    first, last = packets[0], packets[-1]
    assert first["experiments"] == [] and {item["model"] for item in first["clean"]} == {"model-1", "model-2"}
    assert all(item["histories"] == 22 and 0 <= item["detection"] <= 1 for item in first["clean"])
    assert first["criterion"]["model"] == "model-2" and first["criterion"]["minLostWarnings"] == 1
    assert len(last["experiments"]) == 12 and last["omittedCases"] == 2
    assert last["families"] == [{"family": "channel-1:dropout", "experiments": 14, "measuredFailures": 0, "worstDetectionDelta": 0.0}]
    assert all(entry["finding"] in {"no_measured_failure", "measured_failure", "inconclusive", "not_applicable"} for entry in last["experiments"])
    assert len(json.dumps(last)) < 2 * len(json.dumps(packets[12]))


def test_rejected_reasons_reach_the_model_briefly(fitted, tmp_path, monkeypatch):
    fixed, store, investigation, config = setup(fitted, tmp_path)
    store.add_proposals(investigation, [{"components": [component("unknown")]}])
    provider(monkeypatch, lambda packet, count: stop())
    ExperimentRunner(store, fixed).run(investigation)
    calls = provider(monkeypatch, lambda packet, count: stop())
    run(store, fixed, config, investigation)
    assert calls[0]["rejected"]["count"] == 1 and "allowed mapping" in calls[0]["rejected"]["recent"][0]
    assert "unknown" not in json.dumps(calls[0]["experiments"])


def test_seed_suite_spans_profile_groups_and_respects_the_policy(fitted):
    policy = loadPolicy("synthetic-rotating-v1")
    engine = FixedDevelopmentEvaluator(fitted, {LR: .95}, policy)
    seeds = seedSuite(policy, engine.config, 4)
    sensors = [item["scenario"]["components"][0]["sensor"] for item in seeds]
    assert sensors == ["temp_bearing", "pressure_out", "current_draw", "ambient_temp"]
    for item in seeds:
        policy.check(FaultCase.model_validate(item["scenario"]), engine.config)
    assert seedSuite(policy, engine.config, 4) == seeds and len(seedSuite(policy, engine.config, 50)) == 9
    plain = evaluator(fitted).policy
    assert [item["scenario"]["components"][0]["kind"] for item in seedSuite(plain, engine.config)] == ["stuck", "stuck"]


def test_seed_cases_run_through_the_normal_runner(fitted, tmp_path):
    policy = loadPolicy("synthetic-rotating-v1")
    engine = FixedDevelopmentEvaluator(fitted, {LR: .95}, policy)
    store = InvestigationStore(tmp_path / "store")
    investigation = store.create(engine, InvestigationBudget(), seedSuite(policy, engine.config, 3))
    summary = ExperimentRunner(store, engine).run(investigation)
    assert summary.stop_reason == "completed" and len(summary.completed) == 3 and summary.rejected == []


def test_near_identical_discoveries_count_as_one_family(fitted):
    engine = FixedDevelopmentEvaluator(fitted, {LR: .95}, loadPolicy("synthetic-rotating-v1"))
    criterion = FindingCriterion(candidate=LR)
    findings = [classify(engine.evaluate(FaultCase.model_validate({"components": [
        component("vibration_rms", kind="stuck", onset_before_failure=onset), component("oil_particles", kind="stuck", onset_before_failure=onset)]})),
        criterion, attempt_id=f"a{onset}") for onset in (58, 60)]
    assert [finding.status for finding in findings] == ["measured_failure", "measured_failure"]
    summary = summarize(findings)
    assert len(summary["discoveries"]) == 2 and summary["discoveryFamilies"] == ["oil_particles:stuck+vibration_rms:stuck"]


def test_cli_create_can_prepend_seed_cases(fitted, tmp_path, capsys):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("seed_cli", Path(__file__).resolve().parents[1] / "scripts/run_fault_investigation.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    engine = FixedDevelopmentEvaluator(fitted, {LR: .95}, loadPolicy("synthetic-rotating-v1"))
    cli.context = lambda _args: engine
    (tmp_path / "extra.json").write_text(json.dumps([{"components": [component("vibration_rms", kind="stuck")]}]))
    assert cli.main(["--store", str(tmp_path / "store"), "--create", str(tmp_path / "extra.json"), "--seed", "2"]) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["proposals"] == 3
    saved = payloads(InvestigationStore(tmp_path / "store"), created["investigation_id"])
    assert [item["reason"].startswith("Seed suite") for item in saved[:2]] == [True, True]
