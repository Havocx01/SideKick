"""Durable bounded execution of saved fault-scenario proposals."""
import sqlite3
import json

import pytest

from app.faults.evaluator import EvaluationStopped
from app.faults.investigation import (ExperimentRunner, InvestigationBudget, InvestigationBusy, InvestigationError,
    InvestigationStore, LeaseLost)
from test_compound_faults import component, evaluator, fitted as fitted  # noqa: F401


def case(sensor="temp_bearing", **changes):
    return {"components": [component(sensor, **changes)]}


DROPOUT = case()
STUCK = case("vibration_rms", kind="stuck", onset_before_failure=30)
COMPOUND = {"components": [component(), component("vibration_rms", kind="drift", severity_sd=1.5, sign=1, ramp_cycles=10)]}


def setup(fitted, tmp_path, proposals, **budget):
    fixed = evaluator(fitted)
    store = InvestigationStore(tmp_path / "store")
    investigation = store.create(fixed, InvestigationBudget(**budget), proposals)
    return fixed, store, investigation


def statuses(store, investigation):
    return [p.status for p in store.load(investigation).proposals]


def rows(store, sql, *params):
    with sqlite3.connect(store.path) as db:
        return db.execute(sql, params).fetchall()



def test_saved_proposals_are_validated_and_bad_ones_never_run(fitted, tmp_path):
    proposals = [DROPOUT, case("unknown"), case(kind="drift", severity_sd=9.0, sign=1, ramp_cycles=10),
        "{not json", {"components": []}, {"components": [component()], "extra": 1}]
    fixed, store, investigation = setup(fitted, tmp_path, proposals)
    summary = ExperimentRunner(store, fixed).run(investigation)
    state = store.load(investigation)
    assert summary.stop_reason == "completed" and summary.slots_used == 1 and len(summary.rejected) == 5
    assert statuses(store, investigation) == ["completed"] + ["rejected"] * 5
    reasons = [p.reason for p in state.proposals[1:]]
    assert "allowed mapping" in reasons[0] and "severity" in reasons[1]
    assert all(r and len(r) <= 300 for r in reasons)
    assert not any(a.proposal_id in summary.rejected for a in state.attempts)


def test_saved_result_matches_the_fixed_evaluator_and_is_integrity_checked(fitted, tmp_path):
    fixed, store, investigation = setup(fitted, tmp_path, [COMPOUND])
    attempt = ExperimentRunner(store, fixed).run(investigation).completed[0]
    from app.faults.scenarios import FaultCase
    assert store.result(attempt).model_dump() == evaluator(fitted).evaluate(FaultCase.model_validate(COMPOUND)).model_dump()
    rows(store, "UPDATE attempts SET result=replace(result,'complete','partial') WHERE id=?", attempt)
    with pytest.raises(ValueError, match="checksum"):
        store.result(attempt)


def test_investigation_is_bound_to_its_fitted_context_and_policy(fitted, tmp_path):
    fixed, store, investigation = setup(fitted, tmp_path, [DROPOUT])
    from app.faults.evaluator import FixedDevelopmentEvaluator
    other = FixedDevelopmentEvaluator(fitted, {"logistic_regression/lr-probe": .4}, fixed.policy)
    with pytest.raises(InvestigationError, match="context"):
        ExperimentRunner(store, other).run(investigation)
    with pytest.raises(InvestigationError, match="policy"):
        ExperimentRunner(store, evaluator(fitted, max_components=1)).run(investigation)
    with pytest.raises(ValueError, match="evaluation limit"):
        store.create(evaluator(fitted, max_evaluations=2), InvestigationBudget(max_experiments=3))
    assert store.load(investigation).slots_used == 0



def test_slot_is_reserved_and_running_before_the_evaluator_starts(fitted, tmp_path, monkeypatch):
    fixed, store, investigation = setup(fitted, tmp_path, [DROPOUT, STUCK], max_experiments=1, max_failures=1)
    original, seen = fixed.evaluate, []
    def observe(scenario, *, cancelled=None):
        seen.append(rows(store, "SELECT status, started IS NOT NULL FROM attempts WHERE investigation=?", investigation))
        return original(scenario, cancelled=cancelled)
    monkeypatch.setattr(fixed, "evaluate", observe)
    summary = ExperimentRunner(store, fixed).run(investigation)
    assert seen == [[("running", 1)]]
    assert summary.stop_reason == "budget_exhausted" and summary.slots_used == 1
    assert statuses(store, investigation) == ["completed", "pending"]


def test_budget_holds_across_runs_and_a_later_run_continues(fitted, tmp_path):
    fixed, store, investigation = setup(fitted, tmp_path, [DROPOUT, STUCK, COMPOUND], max_experiments=2, max_failures=1)
    assert ExperimentRunner(store, fixed).run(investigation).slots_used == 2
    again = ExperimentRunner(store, evaluator(fitted)).run(investigation)
    assert again.stop_reason == "budget_exhausted" and again.completed == []
    assert statuses(store, investigation) == ["completed", "completed", "pending"]



def test_duplicates_are_skipped_within_and_across_runs_without_slots(fitted, tmp_path):
    reordered = {"components": list(reversed(COMPOUND["components"]))}
    fixed, store, investigation = setup(fitted, tmp_path, [COMPOUND, reordered, COMPOUND])
    first = ExperimentRunner(store, fixed).run(investigation)
    assert first.slots_used == 1 and len(first.duplicates) == 2
    owner = store.load(investigation).proposals[0].id
    assert {p.duplicate_of for p in store.load(investigation).proposals[1:]} == {owner}
    store.add_proposals(investigation, [COMPOUND, DROPOUT])
    second = ExperimentRunner(store, fixed).run(investigation)
    assert len(second.duplicates) == 1 and len(second.completed) == 1 and second.slots_used == 2


def test_failed_attempts_are_counted_retried_then_exhausted(fitted, tmp_path, monkeypatch):
    fixed, store, investigation = setup(fitted, tmp_path, [DROPOUT, STUCK], max_experiments=8, max_failures=5, max_attempts_per_scenario=2)
    original, order = fixed.evaluate, []
    def flaky(scenario, *, cancelled=None):
        order.append(scenario.components[0].sensor)
        if scenario.components[0].sensor == "temp_bearing":
            raise ValueError("Fitted model returned invalid prediction scores")
        return original(scenario, cancelled=cancelled)
    monkeypatch.setattr(fixed, "evaluate", flaky)
    summary = ExperimentRunner(store, fixed).run(investigation)
    # The untried scenario runs before the failed one is retried.
    assert order == ["temp_bearing", "vibration_rms", "temp_bearing"]
    assert summary.failures == 2 and summary.slots_used == 3 and summary.stop_reason == "completed"
    state = store.load(investigation)
    assert [p.status for p in state.proposals] == ["exhausted", "completed"] and state.proposals[0].failed_attempts == 2
    assert [a.reason for a in state.attempts if a.status == "failed"] == ["ValueError: Fitted model returned invalid prediction scores"] * 2


def test_failure_limit_stops_the_investigation(fitted, tmp_path, monkeypatch):
    fixed, store, investigation = setup(fitted, tmp_path, [DROPOUT, STUCK, COMPOUND], max_failures=2, max_attempts_per_scenario=1)
    monkeypatch.setattr(fixed, "evaluate", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))
    summary = ExperimentRunner(store, fixed).run(investigation)
    assert summary.stop_reason == "failure_limit" and summary.failures == 2
    assert statuses(store, investigation) == ["exhausted", "exhausted", "pending"]



def test_cancel_before_start_uses_no_slot_and_resume_continues(fitted, tmp_path):
    fixed, store, investigation = setup(fitted, tmp_path, [DROPOUT])
    store.request_cancel(investigation)
    assert ExperimentRunner(store, fixed).run(investigation).stop_reason == "cancelled"
    assert store.load(investigation).slots_used == 0
    store.resume(investigation)
    assert ExperimentRunner(store, fixed).run(investigation).stop_reason == "completed"


def test_cancel_after_reservation_but_before_start_releases_the_slot(fitted, tmp_path):
    fixed, store, investigation = setup(fitted, tmp_path, [DROPOUT])
    calls = iter([False, True])
    summary = ExperimentRunner(store, fixed).run(investigation, cancelled=lambda: next(calls, True))
    assert summary.stop_reason == "cancelled" and summary.slots_used == 0 and store.load(investigation).attempts == []


def test_cancel_during_execution_is_recorded_without_counting_a_failure(fitted, tmp_path):
    fixed, store, investigation = setup(fitted, tmp_path, [COMPOUND])
    checks = 0
    def cancel():
        nonlocal checks
        checks += 1
        return checks > 6
    summary = ExperimentRunner(store, fixed).run(investigation, cancelled=cancel)
    state = store.load(investigation)
    assert summary.stop_reason == "cancelled" and state.failures == 0 and state.slots_used == 1
    assert [a.status for a in state.attempts] == ["cancelled"] and statuses(store, investigation) == ["pending"]
    assert ExperimentRunner(store, fixed).run(investigation).stop_reason == "completed"


def test_cross_process_cancel_reaches_a_running_experiment(fitted, tmp_path, monkeypatch):
    fixed, store, investigation = setup(fitted, tmp_path, [COMPOUND])
    original = fixed.evaluate
    def evaluate(scenario, *, cancelled=None):
        InvestigationStore(tmp_path / "store").request_cancel(investigation)  # A second process asks to stop.
        return original(scenario, cancelled=cancelled)
    monkeypatch.setattr(fixed, "evaluate", evaluate)
    ticks = iter(range(0, 10_000, 2))
    summary = ExperimentRunner(store, fixed, monotonic=lambda: float(next(ticks))).run(investigation)
    assert summary.stop_reason == "cancelled" and [a.status for a in store.load(investigation).attempts] == ["cancelled"]


def test_run_time_limit_stops_without_blaming_the_scenario(fitted, tmp_path):
    fixed, store, investigation = setup(fitted, tmp_path, [COMPOUND, DROPOUT], max_run_seconds=10)
    clock = iter([0.0] + [1.0] * 4 + [11.0] * 10_000)
    summary = ExperimentRunner(store, fixed, monotonic=lambda: next(clock)).run(investigation)
    state = store.load(investigation)
    assert summary.stop_reason == "time_limit" and state.failures == 0
    assert [a.status for a in state.attempts] == ["stopped"] and statuses(store, investigation) == ["pending", "pending"]
    expired = iter([0.0, 11.0] + [11.0] * 100)
    assert ExperimentRunner(store, fixed, monotonic=lambda: next(expired)).run(investigation).stop_reason == "time_limit"
    assert store.load(investigation).slots_used == 1


def test_experiment_time_limit_is_a_counted_failure(fitted, tmp_path, monkeypatch):
    fixed, store, investigation = setup(fitted, tmp_path, [DROPOUT], max_attempts_per_scenario=1)
    def slow(*_a, **_k):
        raise EvaluationStopped("Evaluation cancelled or cooperative time limit reached")
    monkeypatch.setattr(fixed, "evaluate", slow)
    summary = ExperimentRunner(store, fixed).run(investigation)
    assert summary.failures == 1 and [a.status for a in store.load(investigation).attempts] == ["timed_out"]
    assert statuses(store, investigation) == ["exhausted"]


def test_interrupted_run_is_recovered_counted_and_retried(fitted, tmp_path, monkeypatch):
    fixed, store, investigation = setup(fitted, tmp_path, [DROPOUT, STUCK])
    with monkeypatch.context() as scoped:
        scoped.setattr(fixed, "evaluate", lambda *_a, **_k: (_ for _ in ()).throw(KeyboardInterrupt()))
        with pytest.raises(KeyboardInterrupt):
            ExperimentRunner(store, fixed).run(investigation)
    assert [a.status for a in store.load(investigation).attempts] == ["running"]
    summary = ExperimentRunner(store, fixed).run(investigation)
    state = store.load(investigation)
    assert len(summary.interrupted_recovered) == 1 and state.failures == 1
    assert [a.status for a in state.attempts] == ["interrupted", "completed", "completed"]
    assert statuses(store, investigation) == ["completed", "completed"]


def test_crashed_runner_lease_blocks_until_expiry_and_orphaned_reservations_are_released(fitted, tmp_path):
    fixed, store, investigation = setup(fitted, tmp_path, [DROPOUT])
    proposal = store.load(investigation).proposals[0].id
    rows(store, "UPDATE investigation_runs SET lease_token='dead', lease_expires=? WHERE id=?", 1_000.0, investigation)
    rows(store, "INSERT INTO attempts(id,investigation,proposal,scenario_id,status,lease_token,reserved) VALUES('r',?,?,'x','reserved','dead',1)",
        investigation, proposal)
    with pytest.raises(InvestigationBusy):
        ExperimentRunner(store, fixed, wall=lambda: 999.0).run(investigation)
    summary = ExperimentRunner(store, fixed).run(investigation)
    assert summary.slots_used == 1 and summary.interrupted_recovered == []
    assert [a.status for a in store.load(investigation).attempts] == ["completed"]


def test_a_runner_that_loses_its_lease_cannot_record_results(fitted, tmp_path, monkeypatch):
    fixed, store, investigation = setup(fitted, tmp_path, [COMPOUND])
    original = fixed.evaluate
    def evaluate(scenario, *, cancelled=None):
        rows(store, "UPDATE investigation_runs SET lease_token='successor', lease_expires=9e12 WHERE id=?", investigation)
        return original(scenario, cancelled=cancelled)
    monkeypatch.setattr(fixed, "evaluate", evaluate)
    ticks = iter(range(0, 10_000, 2))
    with pytest.raises(LeaseLost):
        ExperimentRunner(store, fixed, monotonic=lambda: float(next(ticks))).run(investigation)
    assert [a.status for a in store.load(investigation).attempts] == ["running"]
    assert rows(store, "SELECT lease_token FROM investigation_runs WHERE id=?", investigation) == [("successor",)]


def test_runner_attaches_to_existing_records_and_accepts_typed_proposals(fitted, tmp_path):
    from app.investigator.records import InvestigationStore as RecordStore, InvestigationBudget as RecordBudget
    fixed = evaluator(fitted)
    records = RecordStore(tmp_path / "store")
    record = records.create(fixed, objective="Find warning failures.",
        budget=RecordBudget(max_experiments=2, max_proposals=3, max_seconds=120))
    store = InvestigationStore(tmp_path / "store")
    assert store.path == records.path
    assert store.attachRecord(record.id) == record.id
    store.add_proposals(record.id, [{"scenario": DROPOUT, "reason": "Inspect missing temperature readings."}])
    summary = ExperimentRunner(store, fixed).run(record.id)
    assert len(summary.completed) == 1
    assert store.get(record.id) == record
    assert store.load(record.id).budget.max_experiments == 2
    assert store.load(record.id).budget.max_run_seconds == 120
    with pytest.raises(ValueError):
        store.attachRecord(record.id, InvestigationBudget(max_experiments=3, max_run_seconds=121))


def test_attached_runner_obeys_saved_proposal_limit(fitted, tmp_path):
    from app.investigator.records import InvestigationStore as RecordStore, InvestigationBudget as RecordBudget
    fixed = evaluator(fitted)
    record = RecordStore(tmp_path / "store").create(fixed, objective="Test proposal limits.",
        budget=RecordBudget(max_experiments=2, max_proposals=1, max_seconds=120))
    store = InvestigationStore(tmp_path / "store")
    store.attachRecord(record.id)
    store.add_proposals(record.id, [DROPOUT])
    with pytest.raises(ValueError, match="proposal limit"):
        store.add_proposals(record.id, [STUCK])
    assert len(store.load(record.id).proposals) == 1


def test_runner_reuses_strict_proposal_validation(fitted, tmp_path):
    invalid = case(onset_before_failure="40")
    fixed, store, investigation = setup(fitted, tmp_path,
        [invalid, {"scenario": DROPOUT, "reason": "  "}, {"scenario": STUCK, "reason": "Test vibration loss."}])
    summary = ExperimentRunner(store, fixed).run(investigation)
    assert len(summary.rejected) == 2 and len(summary.completed) == 1
    assert summary.slots_used == 1


def test_cancel_arriving_at_start_releases_the_slot(fitted, tmp_path, monkeypatch):
    fixed, store, investigation = setup(fitted, tmp_path, [DROPOUT])
    runner = ExperimentRunner(store, fixed)
    original = runner._start

    def start(*args):
        store.request_cancel(investigation)
        return original(*args)

    monkeypatch.setattr(runner, "_start", start)
    summary = runner.run(investigation)
    assert summary.stop_reason == "cancelled" and summary.slots_used == 0
    assert store.load(investigation).attempts == []


def test_nested_result_identity_is_verified_before_saving(fitted, tmp_path, monkeypatch):
    from app.faults.scenarios import FaultCase
    fixed, store, investigation = setup(fitted, tmp_path, [DROPOUT], max_attempts_per_scenario=1)
    original = fixed.evaluate

    def mismatched(scenario, **kwargs):
        result = original(scenario, **kwargs)
        result.scenario = FaultCase.model_validate(STUCK)
        return result

    monkeypatch.setattr(fixed, "evaluate", mismatched)
    summary = ExperimentRunner(store, fixed).run(investigation)
    assert summary.failures == 1 and summary.completed == []


def test_checked_result_cannot_be_relabelled_with_a_new_checksum(fitted, tmp_path):
    import hashlib
    fixed, store, investigation = setup(fitted, tmp_path, [DROPOUT])
    attempt = ExperimentRunner(store, fixed).run(investigation).completed[0]
    result = store.result(attempt).model_dump(mode="json")
    result["scenario"] = STUCK
    payload = json.dumps(result)
    rows(store, "UPDATE attempts SET result=?,result_digest=? WHERE id=?", payload, hashlib.sha256(payload.encode()).hexdigest(), attempt)
    with pytest.raises(ValueError, match="investigation"):
        store.result(attempt)


def test_deadline_arriving_before_start_releases_the_slot(fitted, tmp_path, monkeypatch):
    fixed, store, investigation = setup(fitted, tmp_path, [DROPOUT])
    runner = ExperimentRunner(store, fixed)
    original = runner._start

    def start(investigation, token, attempt, deadline):
        return original(investigation, token, attempt, 0)

    monkeypatch.setattr(runner, "_start", start)
    summary = runner.run(investigation)
    assert summary.stop_reason == "time_limit" and summary.slots_used == 0
    assert store.load(investigation).attempts == []


def test_modified_runner_budget_cannot_exceed_the_saved_record(fitted, tmp_path):
    fixed, store, investigation = setup(fitted, tmp_path, [DROPOUT], max_experiments=3, max_run_seconds=120)
    budget = store.load(investigation).budget.model_dump()
    budget["max_experiments"] = 4
    rows(store, "UPDATE investigation_runs SET budget=? WHERE id=?", json.dumps(budget), investigation)
    with pytest.raises(InvestigationError, match="saved investigation budget"):
        ExperimentRunner(store, fixed).run(investigation)
    assert store.load(investigation).slots_used == 0


def test_invalid_initial_proposals_leave_no_partial_record(fitted, tmp_path):
    fixed = evaluator(fitted)
    store = InvestigationStore(tmp_path / "store")
    with pytest.raises(ValueError, match="proposal limit"):
        store.create(fixed, proposals=[DROPOUT] * 257)
    assert rows(store, "SELECT count(*) FROM investigations") == [(0,)]
    assert rows(store, "SELECT count(*) FROM investigation_runs") == [(0,)]


def test_two_runners_cannot_execute_the_same_investigation(fitted, tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    fixed, store, investigation = setup(fitted, tmp_path, [DROPOUT])
    entered, released = Event(), Event()
    original = fixed.evaluate

    def evaluate(scenario, **kwargs):
        entered.set()
        assert released.wait(5)
        return original(scenario, **kwargs)

    monkeypatch.setattr(fixed, "evaluate", evaluate)
    with ThreadPoolExecutor(max_workers=1) as pool:
        run = pool.submit(ExperimentRunner(store, fixed).run, investigation)
        try:
            assert entered.wait(5)
            with pytest.raises(InvestigationBusy):
                ExperimentRunner(InvestigationStore(tmp_path / "store"), evaluator(fitted)).run(investigation)
        finally:
            released.set()
        assert len(run.result(timeout=5).completed) == 1
    assert store.load(investigation).slots_used == 1
