import json
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from app.faults.evaluator import FixedDevelopmentEvaluator
from app.faults.investigation import ExperimentRunner, InvestigationBudget, InvestigationStore
from app.faults.profiles import loadPolicy
from app.faults.remote import JobManifest, RemoteExecutor, RemoteJobError, canonical, runJob, sha
from app.faults.replay import export_evaluation
from app.faults.scenarios import FaultCase
from test_compound_faults import component, fitted as fitted  # noqa: F401

LR = "logistic_regression/lr-probe"
STUCK_PAIR = {"components": [component("vibration_rms", kind="stuck", onset_before_failure=60), component("oil_particles", kind="stuck", onset_before_failure=60)]}
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def remote(fitted, tmp_path):
    engine = FixedDevelopmentEvaluator(fitted, {LR: .95}, loadPolicy("synthetic-rotating-v1", max_evaluations=128))
    export_evaluation(engine, engine.evaluate(FaultCase.model_validate(STUCK_PAIR)), tmp_path / "context")
    store = InvestigationStore(tmp_path / "store")
    investigation = store.create(engine, InvestigationBudget(max_attempts_per_scenario=2), [STUCK_PAIR])
    return engine, store, investigation, tmp_path


class Worker:
    def __init__(self, root, *, copies=1, before=None, context=None):
        self.root, self.copies, self.before = root, copies, before
        self.context = context or root / "context"
        self.stop, self.seen = threading.Event(), []
        self.thread = threading.Thread(target=self.loop, daemon=True)

    def loop(self):
        while not self.stop.is_set():
            for path in sorted((self.root / "outbox").glob("*.json")):
                if path.name in self.seen:
                    continue
                self.seen.append(path.name)
                if self.before:
                    self.before(path)
                for _ in range(self.copies):
                    runJob(path, self.context, self.root / "inbox", trusted=True)
            time.sleep(.02)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(5)


def executor(engine, root, **options):
    return RemoteExecutor(engine, root / "context", root / "outbox", root / "inbox", transferConsent=True, poll=.02, **options)


def test_remote_result_matches_local_execution(remote):
    engine, store, investigation, root = remote
    with Worker(root):
        summary = ExperimentRunner(store, engine, execute=executor(engine, root)).run(investigation)
    assert summary.stop_reason == "completed" and len(summary.completed) == 1
    local = engine.evaluate(FaultCase.model_validate(STUCK_PAIR))
    assert store.result(summary.completed[0]).model_dump() == local.model_dump()


def test_duplicate_and_forged_deliveries_never_overwrite_the_accepted_result(remote):
    engine, store, investigation, root = remote
    def forge(path):
        manifest = json.loads(path.read_text())
        forged = {"jobId": manifest["jobId"], "manifestDigest": "0" * 64, "status": "completed", "evaluation": {}, "evaluationDigest": "x"}
        (root / "inbox" / f"{manifest['jobId']}.forged.json").write_text(json.dumps(forged))
    run = executor(engine, root)
    with Worker(root, copies=2, before=forge):
        summary = ExperimentRunner(store, engine, execute=run).run(investigation)
    assert len(summary.completed) == 1 and len(run.jobs) == 1
    assert len(list((root / "inbox").glob(f"{run.jobs[0]}.*.json"))) == 3
    assert store.result(summary.completed[0]).scenario_id == FaultCase.model_validate(STUCK_PAIR).scenario_id
    assert [item.status for item in store.load(investigation).attempts] == ["completed"]


def test_failed_jobs_are_retried_a_bounded_number_of_times_then_counted(remote, fitted):
    engine, store, investigation, root = remote
    other = FixedDevelopmentEvaluator(fitted, {LR: .9}, engine.policy)
    export_evaluation(other, other.evaluate(FaultCase.model_validate(STUCK_PAIR)), root / "other-context")
    run = executor(engine, root, maxAttempts=2)
    started = time.monotonic()
    with Worker(root, context=root / "other-context"):
        summary = ExperimentRunner(store, engine, execute=run).run(investigation)
    assert time.monotonic() - started < 30
    state = store.load(investigation)
    assert len(run.jobs) == 4 and summary.failures == 2
    assert [item.status for item in state.attempts] == ["failed", "failed"] and state.proposals[0].status == "exhausted"
    assert "Remote job failed 2 times" in state.attempts[0].reason and "does not match the manifest" in state.attempts[0].reason


def test_a_late_completion_cannot_bypass_cancellation(remote):
    engine, store, investigation, root = remote
    run = executor(engine, root)
    checks = iter([False] * 6 + [True] * 1000)
    summary = ExperimentRunner(store, engine, execute=run).run(investigation, cancelled=lambda: next(checks))
    assert summary.stop_reason == "cancelled" and [item.status for item in store.load(investigation).attempts] == ["cancelled"]
    runJob(root / "outbox" / f"{run.jobs[0]}.json", root / "context", root / "inbox", trusted=True)
    assert [item.status for item in store.load(investigation).attempts] == ["cancelled"]
    assert store.load(investigation).proposals[0].status == "pending"


def test_missing_workers_time_out_and_tampered_results_are_rejected(remote):
    engine, store, investigation, root = remote
    ticks = iter(range(0, 100000, 1000))
    run = executor(engine, root, maxAttempts=1, clock=lambda: next(ticks), sleep=lambda _seconds: None)
    with pytest.raises(RemoteJobError, match="timed out"):
        run(FaultCase.model_validate(STUCK_PAIR))
    case = FaultCase.model_validate(STUCK_PAIR)
    run = executor(engine, root)
    def tamper(path):
        staging = root / "staging"
        staging.mkdir(exist_ok=True)
        output = runJob(path, root / "context", staging, trusted=True)
        data = json.loads(output.read_text())
        data["evaluation"]["evaluated_histories"] = 1
        output.write_text(json.dumps(data))
        output.replace(root / "inbox" / output.name)
    worker = Worker(root, copies=0, before=tamper)
    worker.seen = [path.name for path in (root / "outbox").glob("*.json")]
    with worker:
        with pytest.raises(RemoteJobError, match="checksum"):
            run(case)


def test_transfer_needs_consent_and_manifests_are_strict(remote):
    engine, store, investigation, root = remote
    with pytest.raises(PermissionError, match="consent"):
        RemoteExecutor(engine, root / "context", root / "outbox", root / "inbox")
    with pytest.raises(ValueError):
        JobManifest.model_validate({"jobId": "not-a-job", "contextFingerprint": "a" * 64, "contextFiles": {}, "policyFingerprint": "b" * 64,
            "sourceDigest": "c", "scenario": STUCK_PAIR, "maxSeconds": 30, "issuedAt": 0})


def test_worker_cli_runs_one_job_under_limits_and_requires_trust(remote):
    engine, store, investigation, root = remote
    run = executor(engine, root, maxAttempts=1)
    manifest = JobManifest(jobId="a" * 32, contextFingerprint=engine.context_fingerprint, contextFiles=run.files,
        policyFingerprint=engine.policy.fingerprint, sourceDigest=__import__("app.experiments.provenance", fromlist=["x"]).source_digest(),
        scenario=FaultCase.model_validate(STUCK_PAIR), maxSeconds=30, issuedAt=0)
    path = root / "outbox" / "manual.json"
    path.write_text(canonical(manifest.model_dump(mode="json")))
    command = [sys.executable, str(ROOT / "scripts/run_fault_job.py"), "--manifest", str(path), "--context", str(root / "context"),
        "--inbox", str(root / "inbox"), "--cpu-seconds", "120", "--memory-mb", "4096"]
    untrusted = subprocess.run(command, capture_output=True, text=True, timeout=120, cwd=ROOT)
    assert untrusted.returncode == 0
    assert json.loads(Path(untrusted.stdout.strip()).read_text())["status"] == "failed"
    trusted = subprocess.run([*command, "--trust-local-artifact"], capture_output=True, text=True, timeout=120, cwd=ROOT)
    result = json.loads(Path(trusted.stdout.strip()).read_text())
    assert result["status"] == "completed" and result["manifestDigest"] == sha(path.read_text())
    assert result["evaluation"]["scenario_id"] == manifest.scenario.scenario_id


def test_cli_runs_through_remote_workers_only_with_transfer_consent(remote, capsys):
    import importlib.util
    engine, store, investigation, root = remote
    spec = importlib.util.spec_from_file_location("remote_cli", ROOT / "scripts/run_fault_investigation.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    cli.context = lambda _args: engine
    command = ["--store", str(root / "store"), "--context", str(root / "context"), "--run", investigation,
        "--remote-outbox", str(root / "outbox"), "--remote-inbox", str(root / "inbox")]
    with pytest.raises(PermissionError, match="consent"):
        cli.main(command)
    with Worker(root):
        assert cli.main([*command, "--allow-transfer"]) == 0
    assert json.loads(capsys.readouterr().out)["stop_reason"] == "completed"
    assert len(list((root / "outbox").glob("*.json"))) == 1
