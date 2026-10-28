"""Durable investigation metadata before any agent execution is available."""
from dataclasses import replace
import sqlite3

import pytest

from app.config import EXPERIMENT
from app.data.synthetic import make_synthetic_dataset
from app.faults.evaluator import FixedDevelopmentEvaluator
from app.faults.scenarios import FaultPolicy
from app.models.candidates import AgeBaselineCandidate
from app.models.train import train_development


@pytest.fixture(scope="module")
def engine():
    config = replace(EXPERIMENT, holdout_engines=4, n_folds=2, feature_window=5,
        horizon_cycles=20, min_useful_lead=5, late_window_end=4, transition_band_end=30, configs_per_candidate=1)
    training = train_development(make_synthetic_dataset(n_equipment=26, min_life=85, max_life=100, config=config),
        config=config, candidates=[AgeBaselineCandidate("record-probe")])
    return FixedDevelopmentEvaluator(training, {"age_baseline/record-probe": 60.0},
        FaultPolicy(allowed_sensors=("temp_bearing", "vibration_rms"), max_evaluations=4))


def create(store, engine, **changes):
    from app.investigator.records import InvestigationBudget
    return store.create(engine, objective="Find missed warnings under combined measurement faults.",
        budget=InvestigationBudget(max_experiments=3, max_proposals=6, max_seconds=120), **changes)


def test_reopen_preserves_fixed_metadata_and_performs_no_execution(tmp_path, engine, monkeypatch):
    from app.investigator.records import InvestigationStore
    monkeypatch.setattr(engine, "evaluate", lambda *_a, **_k: pytest.fail("Record creation ran an experiment"))
    store = InvestigationStore(tmp_path)
    record = create(store, engine)
    reopened = InvestigationStore(tmp_path).get(record.id)
    assert reopened == record
    reopened.check_context(engine)
    assert record.context_fingerprint == engine.context_fingerprint
    assert record.policy == engine.policy
    assert {item.candidate: item.threshold for item in record.thresholds} == engine.thresholds
    assert record.status == "ready" and record.partition == "out_of_fold"
    assert len(record.history) == 1 and record.history[0].kind == "created"
    assert record.history[0].occurred_at == record.created_at
    assert record.budget.max_experiments == 3
    assert list(tmp_path.iterdir()) == [store.path]


@pytest.mark.parametrize("changes", [{"max_experiments": 0}, {"max_experiments": True},
    {"max_experiments": 129}, {"max_proposals": 0}, {"max_proposals": 257},
    {"max_seconds": 0}, {"max_seconds": float("inf")}, {"max_seconds": True}, {"max_seconds": 3601}])
def test_invalid_budgets_are_rejected(changes):
    from app.investigator.records import InvestigationBudget
    with pytest.raises(ValueError):
        InvestigationBudget(**{"max_experiments": 3, "max_proposals": 6, "max_seconds": 120, **changes})


def test_policy_budget_and_objective_are_checked_before_writing(tmp_path, engine):
    from app.investigator.records import InvestigationBudget, InvestigationStore
    store = InvestigationStore(tmp_path)
    for objective, experiments in [(" ", 3), ("x" * 2001, 3), ("Test", 5)]:
        with pytest.raises(ValueError):
            store.create(engine, objective=objective,
                budget=InvestigationBudget(max_experiments=experiments, max_proposals=6, max_seconds=120))
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT count(*) FROM investigations").fetchone()[0] == 0


def test_record_is_immutable_and_context_changes_are_rejected(tmp_path, engine):
    from app.investigator.records import InvestigationRecord, InvestigationStore
    store = InvestigationStore(tmp_path)
    record = create(store, engine)
    with pytest.raises(ValueError):
        record.objective = "Changed"
    with pytest.raises(ValueError):
        record.budget.max_experiments = 99
    with pytest.raises(ValueError):
        record.thresholds[0].threshold = 1
    for changes in [{"context_fingerprint": "0" * 64}, {"config_fingerprint": "0" * 16},
            {"policy": {**record.policy.model_dump(mode="json"), "max_evaluations": 3}},
            {"thresholds": [{"candidate": record.thresholds[0].candidate, "threshold": 61}]}]:
        changed = InvestigationRecord.model_validate({**record.model_dump(mode="json"), **changes})
        with pytest.raises(ValueError, match="context"):
            changed.check_context(engine)
    assert store.get(record.id) == record


def test_capacity_is_shared_across_store_instances_without_overwrite(tmp_path, engine):
    from app.investigator.records import InvestigationCapacityError, InvestigationStore
    first = InvestigationStore(tmp_path, max_records=1)
    record = create(first, engine)
    with pytest.raises(InvestigationCapacityError):
        create(InvestigationStore(tmp_path, max_records=1), engine)
    assert first.get(record.id) == record


def test_concurrent_creates_cannot_overrun_capacity(tmp_path, engine):
    from concurrent.futures import ThreadPoolExecutor
    from app.investigator.records import InvestigationCapacityError, InvestigationStore
    stores = [InvestigationStore(tmp_path, max_records=1) for _ in range(2)]

    def attempt(store):
        try:
            return create(store, engine).id
        except InvestigationCapacityError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, stores))
    ids = [id for id in results if id is not None]
    assert len(ids) == 1
    assert stores[0].get(ids[0]).id == ids[0]


def test_unchecked_budget_copy_is_revalidated_before_persistence(tmp_path, engine):
    from app.investigator.records import InvestigationBudget, InvestigationStore
    budget = InvestigationBudget(max_experiments=3, max_proposals=6, max_seconds=120)
    invalid = budget.model_copy(update={"max_experiments": 0})
    store = InvestigationStore(tmp_path)
    with pytest.raises(ValueError):
        store.create(engine, objective="Test", budget=invalid)
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT count(*) FROM investigations").fetchone()[0] == 0


def test_unknown_and_invalid_ids_fail_without_path_access(tmp_path, engine):
    from uuid import uuid4
    from app.investigator.records import InvestigationStore
    store = InvestigationStore(tmp_path)
    with pytest.raises(KeyError):
        store.get(str(uuid4()))
    with pytest.raises(ValueError):
        store.get("../workspace.sqlite3")


@pytest.mark.parametrize("payload", ['{"version": 9}', 'not json', 'x' * 131073], ids=["unknown-version", "invalid-json", "oversized"])
def test_unreadable_records_fail_closed(tmp_path, engine, payload):
    from app.investigator.records import InvestigationStore
    store = InvestigationStore(tmp_path)
    record = create(store, engine)
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE investigations SET payload=? WHERE id=?", (payload, record.id))
    with pytest.raises(ValueError):
        store.get(record.id)


def test_row_identity_mismatch_is_rejected(tmp_path, engine):
    from uuid import uuid4
    from app.investigator.records import InvestigationStore
    store = InvestigationStore(tmp_path)
    record = create(store, engine)
    other = str(uuid4())
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE investigations SET id=? WHERE id=?", (other, record.id))
    with pytest.raises(ValueError, match="identity"):
        store.get(other)
