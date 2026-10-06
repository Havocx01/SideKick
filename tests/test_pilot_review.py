"""Pilot records cannot turn synthetic or retrospective tests into field approval."""

import io
import json
import zipfile
from uuid import uuid4

import pytest
from app.evidence.bundle import load_bundle
from app.experiments.store import Workspace
from app.schemas import ExperimentProtocol, FaultScenario, FrozenModelRecord, ValidationRecord


@pytest.fixture
def pilot_case(tmp_path):
    from pathlib import Path

    loaded = load_bundle(Path(__file__).resolve().parents[1] / "evidence/bundle.json")
    loaded.experiment_id = str(uuid4())
    loaded.dataset_id = str(uuid4())
    loaded.source_digest = "source-a"
    loaded.protocol = ExperimentProtocol(scenarios=[FaultScenario(fault=next(r.fault for r in loaded.scenario_results if r.required and r.fault))])
    loaded.final_evaluation = None
    workspace = Workspace(tmp_path)
    workspace.reserve({"experiment_id": loaded.experiment_id, "dataset_id": loaded.dataset_id,
        "source": "upload", "status": "completed", "source_digest": loaded.source_digest})
    payload = {"brief": {"equipment_family": "Motor family A", "reviewing_engineer": "Engineer A",
        "current_procedure": "Review spreadsheets", "intended_decision": "Choose a supervised trial candidate",
        "success_measure": "Review minutes and missed fault cases", "data_classification": "field"},
        "single_family_confirmed": True, "failure_labels_checked": True,
        "representative_data_confirmed": True, "protocol_agreed": True}
    return workspace, loaded, payload


def complete_validation(loaded):
    selected = loaded.development_selection.recommended
    loaded.final_evaluation = loaded.development_selection.model_copy(deep=True)
    loaded.final_evaluation.ranked = [selected.model_copy(deep=True)]
    loaded.frozen_model = FrozenModelRecord(freeze_id="freeze-a", experiment_id=loaded.experiment_id,
        job_id=str(uuid4()), candidate=f"{selected.candidate.value}/{selected.config_id}",
        status="completed", artifact_digest="artifact-a", created_at=1)
    loaded.validation = ValidationRecord(validation_id="validation-a", experiment_id=loaded.experiment_id,
        freeze_id="freeze-a", job_id=str(uuid4()), status="completed", untouched_confirmed=True,
        exposure_started_at=2, created_at=1)


def outcome(**changes):
    return {"reviewing_engineer": "Engineer A", "decision": "supervised_trial",
        "decision_changed": True, "observations": "Sensor failure evidence changed the shortlist.",
        "baseline_review_minutes": 30, "sidekick_review_minutes": 20,
        "evidence_reviewed": True, **changes}


def test_agreement_bound_to_evidence_and_persists(pilot_case):
    from app.experiments.pilot import agree, state
    from app.schemas import PilotAgreementCreate

    workspace, loaded, payload = pilot_case
    record = agree(workspace, loaded, PilotAgreementCreate.model_validate(payload))
    assert record.config_fingerprint == loaded.config_fingerprint
    assert record.data_hash == loaded.profile.data_hash
    assert record.candidate.endswith("/" + loaded.development_selection.recommended.config_id)
    assert state(Workspace(workspace.root), loaded).agreement == record
    with pytest.raises(ValueError, match="already"):
        agree(workspace, loaded, PilotAgreementCreate.model_validate(payload))


def test_agreement_requires_checked_data_and_precedes_scoring(pilot_case):
    from app.experiments.pilot import agree
    from app.schemas import PilotAgreementCreate

    workspace, loaded, payload = pilot_case
    for field in ("single_family_confirmed", "failure_labels_checked", "representative_data_confirmed", "protocol_agreed"):
        with pytest.raises(ValueError):
            PilotAgreementCreate.model_validate({**payload, field: False})
    with pytest.raises(ValueError):
        PilotAgreementCreate.model_validate({**payload, "brief": {**payload["brief"], "equipment_family": "  "}})
    complete_validation(loaded)
    with pytest.raises(ValueError, match="before reserved scoring"):
        agree(workspace, loaded, PilotAgreementCreate.model_validate(payload))


def test_synthetic_cannot_be_declared_field_data(pilot_case):
    from app.experiments.pilot import agree
    from app.schemas import PilotAgreementCreate

    workspace, loaded, payload = pilot_case
    with workspace.connect() as connection:
        connection.execute("UPDATE experiments SET payload=json_set(payload,'$.source','synthetic')")
    with pytest.raises(ValueError, match="Synthetic"):
        agree(workspace, loaded, PilotAgreementCreate.model_validate(payload))


def test_review_requires_independent_results_and_cannot_override_failure(pilot_case):
    from app.experiments.pilot import agree, review
    from app.schemas import PilotAgreementCreate, PilotOutcomeCreate

    workspace, loaded, payload = pilot_case
    agree(workspace, loaded, PilotAgreementCreate.model_validate(payload))
    with pytest.raises(ValueError, match="completed reserved"):
        review(workspace, loaded, PilotOutcomeCreate.model_validate(outcome()))
    complete_validation(loaded)
    loaded.final_evaluation.ranked[0].qualifies = False
    with pytest.raises(ValueError, match="did not meet"):
        review(workspace, loaded, PilotOutcomeCreate.model_validate(outcome()))
    record = review(workspace, loaded, PilotOutcomeCreate.model_validate(outcome(decision="revise_model")))
    assert record.final_qualifies is False
    assert record.validation_id == "validation-a"
    assert record.review_minutes_saved == 10
    with pytest.raises(ValueError, match="already"):
        review(workspace, loaded, PilotOutcomeCreate.model_validate(outcome(decision="collect_data")))


def test_review_rejects_different_evidence_and_incomplete_time_pair(pilot_case):
    from app.experiments.pilot import agree, review
    from app.schemas import PilotAgreementCreate, PilotOutcomeCreate

    workspace, loaded, payload = pilot_case
    agree(workspace, loaded, PilotAgreementCreate.model_validate(payload))
    complete_validation(loaded)
    loaded.config_fingerprint = "different-protocol"
    with pytest.raises(ValueError, match="no longer matches"):
        review(workspace, loaded, PilotOutcomeCreate.model_validate(outcome()))
    with pytest.raises(ValueError, match="both review times"):
        PilotOutcomeCreate.model_validate(outcome(sidekick_review_minutes=None))
    with pytest.raises(ValueError):
        PilotOutcomeCreate.model_validate(outcome(baseline_review_minutes=-1))


def test_export_contains_readable_pilot_and_escaped_review(pilot_case):
    from app.experiments.export import export_zip
    from app.experiments.pilot import agree, review, state
    from app.schemas import PilotAgreementCreate, PilotOutcomeCreate

    workspace, loaded, payload = pilot_case
    agree(workspace, loaded, PilotAgreementCreate.model_validate(payload))
    complete_validation(loaded)
    review(workspace, loaded, PilotOutcomeCreate.model_validate(outcome(observations="<script>bad()</script>")))
    loaded.pilot_review = state(workspace, loaded).record
    with zipfile.ZipFile(io.BytesIO(export_zip(loaded))) as archive:
        html = archive.read("decision-report.html").decode()
        assert "Motor family A" in html
        assert "Engineer review" in html
        assert "&lt;script&gt;" in html and "<script>bad" not in html
        assert "self-reported" in html
        assert "deployment approval" in html
        exported = json.loads(archive.read("pilot-review.json"))
        assert exported["outcome"]["validation_id"] == "validation-a"
        assert exported["agreement"]["config_fingerprint"] == loaded.config_fingerprint


def test_experiments_never_share_review_records(pilot_case):
    from app.experiments.pilot import agree, state
    from app.schemas import PilotAgreementCreate

    workspace, loaded, payload = pilot_case
    agree(workspace, loaded, PilotAgreementCreate.model_validate(payload))
    other = loaded.model_copy(deep=True, update={"experiment_id": str(uuid4())})
    assert state(workspace, other).record is None
