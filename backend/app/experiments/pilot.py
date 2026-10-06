"""A user-declared engineering pilot, bound to immutable experiment evidence."""

import time
from uuid import uuid4

from app.schemas import Partition, PilotAgreementRecord, PilotOutcomeRecord, PilotReviewRecord, PilotState


DECISIONS = {"supervised_trial": "Consider a supervised site trial", "revise_model": "Revise the model",
             "collect_data": "Collect more data", "stop": "Do not proceed"}


def candidate_key(verdict):
    return f"{verdict.candidate.value}/{verdict.config_id}"


def agreement_block(loaded):
    if loaded.validation and loaded.validation.exposure_started_at is not None:
        return "Agree the pilot before reserved scoring begins. Start a new experiment with fresh histories."
    if loaded.final_evaluation is not None:
        return "Agree the pilot before reserved scoring begins. This experiment already has final results."
    if not loaded.protocol or not loaded.source_digest or not loaded.experiment_id or not loaded.dataset_id:
        return "This historical experiment lacks a complete pilot protocol. Start a new experiment."
    if loaded.development_selection.recommended is None:
        return "No candidate met the development limits. Adjust the approach in a new experiment."
    return None


def matching_evidence(loaded, agreement):
    selected = loaded.development_selection.recommended
    if (agreement.experiment_id != loaded.experiment_id or agreement.dataset_id != loaded.dataset_id
            or agreement.data_hash != loaded.profile.data_hash or agreement.config_fingerprint != loaded.config_fingerprint
            or agreement.source_digest != loaded.source_digest or selected is None
            or agreement.candidate != candidate_key(selected)):
        raise ValueError("The evidence no longer matches the agreed pilot. Start a new experiment.")


def review_block(loaded, agreement):
    if agreement is None:
        return "Agree the pilot before recording a review."
    try:
        matching_evidence(loaded, agreement)
    except ValueError as error:
        return str(error)
    if (not loaded.validation or loaded.validation.status != "completed" or loaded.validation.exposure_started_at is None
            or not loaded.frozen_model or loaded.frozen_model.status != "completed"
            or not loaded.final_evaluation or not loaded.final_evaluation.ranked):
        return "A completed reserved evaluation of the frozen model is required before review."
    if (loaded.validation.freeze_id != loaded.frozen_model.freeze_id
            or loaded.validation.experiment_id != agreement.experiment_id
            or loaded.frozen_model.experiment_id != agreement.experiment_id
            or loaded.final_evaluation.partition != Partition.holdout
            or loaded.frozen_model.candidate != agreement.candidate
            or candidate_key(loaded.final_evaluation.ranked[0]) != agreement.candidate
            or not loaded.frozen_model.artifact_digest):
        return "The final result does not match the agreed frozen model."
    return None


def state(workspace, loaded):
    payload = workspace.pilot(loaded.experiment_id) if loaded.experiment_id else None
    record = PilotReviewRecord.model_validate(payload) if payload else None
    agreement = record.agreement if record else None
    outcome = record.outcome if record else None
    blocked = review_block(loaded, agreement)
    final = loaded.final_evaluation
    return PilotState(record=record, agreement=agreement, outcome=outcome,
        phase="complete" if outcome else "review" if agreement and not blocked else "evaluation" if agreement else "agreement",
        agreement_blocked=agreement_block(loaded), review_blocked=blocked,
        final_qualifies=final.ranked[0].qualifies if final and final.ranked else None)


def validate_saved_record(loaded):
    """Do not display or export a saved decision beside incompatible evidence."""
    record = loaded.pilot_review
    if not record:
        return
    matching_evidence(loaded, record.agreement)
    if record.outcome:
        blocked = review_block(loaded, record.agreement)
        if blocked:
            raise ValueError(blocked)
        review = record.outcome
        if (review.agreement_id != record.agreement.agreement_id
                or review.experiment_id != loaded.experiment_id
                or review.validation_id != loaded.validation.validation_id
                or review.freeze_id != loaded.frozen_model.freeze_id
                or review.artifact_digest != loaded.frozen_model.artifact_digest
                or review.final_qualifies != loaded.final_evaluation.ranked[0].qualifies):
            raise ValueError("The recorded review no longer matches the final evidence.")


def agree(workspace, loaded, payload):
    blocked = agreement_block(loaded)
    if blocked:
        raise ValueError(blocked)
    parent = workspace.get("experiments", loaded.experiment_id)
    if parent["status"] != "completed" or parent.get("job_kind", "development") != "development":
        raise ValueError("Complete development before agreeing the pilot.")
    if parent["source"] == "synthetic" and payload.brief.data_classification != "simulated":
        raise ValueError("Synthetic data must remain classified as simulated data.")
    record = PilotAgreementRecord(**payload.model_dump(), agreement_id=str(uuid4()),
        experiment_id=loaded.experiment_id, dataset_id=loaded.dataset_id, data_source=parent["source"],
        data_hash=loaded.profile.data_hash, config_fingerprint=loaded.config_fingerprint,
        source_digest=loaded.source_digest, candidate=candidate_key(loaded.development_selection.recommended), created_at=time.time())
    workspace.save_pilot_part(loaded.experiment_id, "agreement", record.model_dump(mode="json"))
    return record


def review(workspace, loaded, payload):
    existing = state(workspace, loaded)
    if existing.outcome:
        raise ValueError("The pilot outcome is already recorded. Start a new experiment for a different review.")
    if existing.review_blocked:
        raise ValueError(existing.review_blocked)
    selected = loaded.final_evaluation.ranked[0]
    if payload.decision == "supervised_trial" and not selected.qualifies:
        raise ValueError("The frozen model did not meet final limits. Record a revision, more data or a stop decision.")
    if payload.decision == "supervised_trial" and (existing.agreement.data_source != "upload"
            or existing.agreement.brief.data_classification != "field"):
        raise ValueError("A site trial decision requires declared field records. Simulated results support practice only.")
    baseline, sidekick = payload.baseline_review_minutes, payload.sidekick_review_minutes
    record = PilotOutcomeRecord(**payload.model_dump(), review_id=str(uuid4()),
        agreement_id=existing.agreement.agreement_id, experiment_id=loaded.experiment_id,
        validation_id=loaded.validation.validation_id, freeze_id=loaded.frozen_model.freeze_id,
        artifact_digest=loaded.frozen_model.artifact_digest, final_qualifies=selected.qualifies,
        review_minutes_saved=None if baseline is None else baseline - sidekick, created_at=time.time())
    workspace.save_pilot_part(loaded.experiment_id, "outcome", record.model_dump(mode="json"))
    return record
