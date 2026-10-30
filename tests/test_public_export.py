import importlib.util
import json
from pathlib import Path

import pytest

from app.faults.evaluator import FixedDevelopmentEvaluator
from app.faults.investigation import ExperimentRunner, InvestigationBudget, InvestigationStore
from app.faults.profiles import loadPolicy
from app.faults.scenarios import FaultPolicy
from app.investigator.findings import FindingCriterion, digest, recordFindings, saveCriterion
from app.investigator.publication import publicExport
from app.investigator.reduction import reduce
from app.investigator.remedies import compareRemedy
from test_compound_faults import component, fitted as fitted  # noqa: F401
from test_nemotron_controller import provider, proposal, run, stop

LR = "logistic_regression/lr-probe"
SECRET = "Private concern about pump P-104 at the Lagos site"
STUCK_PAIR = {"components": [component("vibration_rms", kind="stuck", onset_before_failure=60), component("oil_particles", kind="stuck", onset_before_failure=60)]}
CASES = [STUCK_PAIR, {"components": [component("temp_bearing")]}, {"components": [component("rated_voltage")]}]


def investigate(fitted, tmp_path, policy=None, cases=CASES):
    engine = FixedDevelopmentEvaluator(fitted, {LR: .95}, policy or loadPolicy("synthetic-rotating-v1", max_evaluations=128))
    store = InvestigationStore(tmp_path / "store")
    investigation = store.create(engine, InvestigationBudget(max_experiments=8), cases, objective=SECRET)
    saveCriterion(store, investigation, FindingCriterion(candidate=LR))
    ExperimentRunner(store, engine).run(investigation)
    return engine, store, investigation


def test_public_export_keeps_evidence_and_drops_private_data(fitted, tmp_path):
    engine, store, investigation = investigate(fitted, tmp_path)
    failure = next(item for item in recordFindings(store, investigation) if item.is_discovery)
    reduce(store, engine, failure.attempt_id, maxExperiments=20)
    compareRemedy(store, engine, investigation, "threshold", threshold=.5)
    evidence = publicExport(store, investigation)
    text = json.dumps(evidence)
    assert SECRET not in text and "P-104" not in text
    assert not any(equipment in text for equipment in fitted.dataset.frame["equipment_id"].unique())
    assert evidence["digest"] == digest({key: value for key, value in evidence.items() if key != "digest"})
    assert evidence["context"]["profile"]["synthetic"] and evidence["context"]["fingerprint"] == engine.context_fingerprint
    assert evidence["proposals"] == {"total": 3, "rejected": 1, "duplicates": 0}
    assert evidence["discoveryFamilies"] == ["oil_particles:stuck+vibration_rms:stuck"]
    experiment = next(item for item in evidence["experiments"] if item["status"] == "measured_failure")
    assert experiment["changedHistories"] > 0 and all(isinstance(effect["histories"], int) for effect in experiment["effects"])
    assert experiment["scenario"]["components"] and experiment["assumptions"]
    assert evidence["reductions"][0]["claims"] and evidence["reductions"][0]["steps"][0]["change"] == "reproduce original"
    remedy = evidence["remedies"][0]
    assert remedy["improved"] >= 1 and all("source" not in row for row in remedy["cases"])
    assert evidence["reproduction"]["public"] and "--profile synthetic-rotating-v1" in evidence["reproduction"]["steps"][0]


def test_public_export_separates_failed_attempts_from_measurements(fitted, tmp_path):
    engine, store, investigation = investigate(fitted, tmp_path, cases=())
    store.add_proposals(investigation, CASES[:2])
    def execute(case, *, cancelled=None):
        if len(case.components) > 1:
            raise RuntimeError(SECRET)
        return engine.evaluate(case, cancelled=cancelled)
    ExperimentRunner(store, engine, execute=execute).run(investigation)
    evidence = publicExport(store, investigation)
    assert len(evidence["experiments"]) == 1 and len(evidence["executionErrors"]) == 2
    assert evidence["experiments"][0]["status"] == "no_measured_failure"
    assert all(item["status"] == "execution_error" for item in evidence["executionErrors"])
    assert SECRET not in json.dumps(evidence)
    assert evidence["digest"] == digest({key: value for key, value in evidence.items() if key != "digest"})


def test_following_the_reproduction_steps_gives_the_same_findings(fitted, tmp_path):
    engine, store, investigation = investigate(fitted, tmp_path)
    evidence = publicExport(store, investigation)
    scenarios = [item["scenario"] for item in evidence["experiments"]]
    criterion = FindingCriterion.model_validate(evidence["criterion"])
    other = FixedDevelopmentEvaluator(fitted, evidence["context"]["thresholds"], loadPolicy(evidence["context"]["profile"]["id"], max_evaluations=128))
    assert other.context_fingerprint == evidence["context"]["fingerprint"]
    again = InvestigationStore(tmp_path / "again")
    rerun = again.create(other, InvestigationBudget(max_experiments=8), scenarios)
    saveCriterion(again, rerun, criterion)
    ExperimentRunner(again, other).run(rerun)
    expected = {item["scenarioId"]: item["status"] for item in evidence["experiments"]}
    assert {item.scenario_id: item.status for item in recordFindings(again, rerun) if item.attempt_id} == expected


def test_non_distributable_contexts_are_not_offered_for_public_replay(fitted, tmp_path):
    policy = FaultPolicy(allowed_sensors=("vibration_rms", "oil_particles", "temp_bearing", "rated_voltage"), max_evaluations=128)
    engine, store, investigation = investigate(fitted, tmp_path, policy)
    evidence = publicExport(store, investigation)
    assert evidence["context"]["profile"] is None and evidence["reproduction"]["public"] is False


def test_controller_identity_is_kept_without_the_objective_or_key(fitted, tmp_path, monkeypatch):
    from test_nemotron_controller import setup
    fixed, store, investigation, config = setup(fitted, tmp_path)
    saveCriterion(store, investigation, FindingCriterion(candidate=LR))
    provider(monkeypatch, [proposal(), stop()])
    run(store, fixed, config, investigation)
    evidence = publicExport(store, investigation)
    assert evidence["controller"]["model"] == "nvidia/nemotron-3-super-120b-a12b" and evidence["controller"]["callsUsed"] == 2
    assert evidence["controller"]["prompt"].startswith("nemotron-fault-search") and evidence["controller"]["reportedCompletionTokens"] == 80
    text = json.dumps(evidence)
    assert '"mock"' not in text and "api_key" not in text and store.get(investigation).objective not in text


def test_cli_and_service_write_the_public_export(fitted, tmp_path, capsys):
    engine, store, investigation = investigate(fitted, tmp_path)
    spec = importlib.util.spec_from_file_location("public_cli", Path(__file__).resolve().parents[1] / "scripts/run_fault_investigation.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    output = tmp_path / "public.json"
    assert cli.main(["--store", str(tmp_path / "store"), "--public-export", investigation, str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["digest"] == json.loads(output.read_text())["digest"]
    from app.investigator.service import InvestigationService
    service = InvestigationService(tmp_path / "service", engine.config)
    with pytest.raises(KeyError):
        service.publicExport("someone-else", investigation)
