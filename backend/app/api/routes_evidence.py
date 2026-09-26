"""Read routes over the evidence bundle."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import _cached_bundle, bundle, settings
from app.config import EXPERIMENT, Settings
from app.schemas import (
    CLEAN_SCENARIO_ID,
    AlertExplanation,
    CalibrationReport,
    CandidateConfig,
    DatasetProfile,
    EvidenceBundle,
    Partition,
    ReplaySeries,
    RunRecord,
    ScenarioResult,
    SelectionResult,
    SplitAssignment,
)

router = APIRouter(prefix="/api", tags=["evidence"])


@router.get("/health")
def health(config: Settings = Depends(settings)) -> dict:
    """Liveness plus what this deployment can actually do."""
    try:
        loaded = _cached_bundle()
        bundleState = {
            "available": True,
            "dataset_id": loaded.profile.dataset_id,
            "config_fingerprint": loaded.config_fingerprint,
            "generated_at": loaded.generated_at.isoformat(),
            "scenario_results": len(loaded.scenario_results),
            "replay_series": len(loaded.replay_series),
        }
    except (HTTPException, FileNotFoundError):
        bundleState = {"available": False}

    return {
        "status": "ok",
        "mode": config.mode,
        "can_train": config.mode == "full",
        "can_upload": config.mode == "full",
        "evidence_guide": True,
        "copilot": "recorded evidence only",
        "bundle": bundleState,
        "note": (
            "This deployment serves recorded evidence. Training, fault injection and "
            "attribution run locally; see the repository for how to reproduce them."
            if config.mode == "replay"
            else "Full local deployment."
        ),
    }


@router.get("/config")
def experiment_config(loaded: EvidenceBundle = Depends(bundle)) -> dict:
    return {
        "config": loaded.config,
        "config_fingerprint": loaded.config_fingerprint,
        "git_commit": loaded.git_commit,
        "source_digest": loaded.source_digest,
        "experiment_id": loaded.experiment_id,
        "holdout_status": loaded.holdout_status,
        "current_code_fingerprint": EXPERIMENT.fingerprint(),
        "matches_current_code": loaded.config_fingerprint == EXPERIMENT.fingerprint(),
    }


@router.get("/profile", response_model=DatasetProfile)
def profile(loaded: EvidenceBundle = Depends(bundle)) -> DatasetProfile:
    return loaded.profile


@router.get("/splits", response_model=SplitAssignment)
def splits(loaded: EvidenceBundle = Depends(bundle)) -> SplitAssignment:
    return loaded.splits


@router.get("/candidates", response_model=list[CandidateConfig])
def candidates(loaded: EvidenceBundle = Depends(bundle)) -> list[CandidateConfig]:
    return loaded.candidates


@router.get("/selection", response_model=SelectionResult)
def selection(loaded: EvidenceBundle = Depends(bundle)) -> SelectionResult:
    return loaded.development_selection


@router.get("/final-evaluation")
def final_evaluation(loaded: EvidenceBundle = Depends(bundle)) -> dict:
    """The single frozen evaluation on the held-out engines, once it has been run."""
    if loaded.final_evaluation is None:
        return {
            "available": False,
            "note": (
                "No final evaluation is attached to this protocol revision. "
                "Development results guide model selection; historical holdout "
                "scores from another revision do not validate the current model."
            ),
        }
    return {"available": True, "selection": loaded.final_evaluation.model_dump(mode="json")}


@router.get("/scenarios", response_model=list[ScenarioResult])
def scenarios(
    loaded: EvidenceBundle = Depends(bundle),
    candidate: str | None = Query(None, description="Candidate family or family/config_id"),
    required_only: bool = Query(False),
    include_clean: bool = Query(True),
    fault_kind: str | None = Query(None),
    sensor: str | None = Query(None),
    partition: Partition = Query(Partition.out_of_fold),
) -> list[ScenarioResult]:
    results = [r for r in loaded.scenario_results if r.partition == partition]
    if candidate:
        results = [r for r in results if candidate in (r.candidate.value, f"{r.candidate.value}/{r.config_id}")]
    if required_only:
        results = [r for r in results if r.required or (include_clean and r.scenario_id == CLEAN_SCENARIO_ID)]
    if not include_clean:
        results = [r for r in results if r.scenario_id != CLEAN_SCENARIO_ID]
    if fault_kind:
        results = [r for r in results if r.fault and r.fault.kind.value == fault_kind]
    if sensor:
        results = [r for r in results if r.fault and r.fault.sensor == sensor]
    return results


@router.get("/calibration", response_model=list[CalibrationReport])
def calibration(loaded: EvidenceBundle = Depends(bundle)) -> list[CalibrationReport]:
    return loaded.calibration


@router.get("/replay/index")
def replay_index(loaded: EvidenceBundle = Depends(bundle)) -> dict:
    """What replay series the bundle contains, for populating the selector."""
    entries = [
        {
            "equipment_id": s.equipment_id,
            "candidate": s.candidate.value,
            "config_id": s.config_id,
            "scenario_id": s.scenario_id,
            "fault": s.fault.label() if s.fault else None,
            "detected": s.outcome.detected,
            "late": s.outcome.late,
            "missed": s.outcome.missed,
            "lead_time": s.outcome.lead_time,
            "episodes": len(s.episodes),
            "cycles": len(s.points),
        }
        for s in loaded.replay_series
    ]
    return {
        "series": entries,
        "equipment": sorted({e["equipment_id"] for e in entries}),
        "scenarios": sorted({e["scenario_id"] for e in entries}),
    }


@router.get("/replay", response_model=list[ReplaySeries])
def replay(
    loaded: EvidenceBundle = Depends(bundle),
    equipment_id: str | None = Query(None),
    scenario_id: str | None = Query(None),
) -> list[ReplaySeries]:
    series = loaded.replay_series
    if equipment_id:
        series = [s for s in series if s.equipment_id == equipment_id]
    if scenario_id:
        series = [s for s in series if s.scenario_id == scenario_id]
    if not series:
        raise HTTPException(status_code=404, detail="no replay series matches that request")
    return series


@router.get("/explanations", response_model=list[AlertExplanation])
def explanations(
    loaded: EvidenceBundle = Depends(bundle), equipment_id: str | None = Query(None)
) -> list[AlertExplanation]:
    items = loaded.explanations
    if equipment_id:
        items = [e for e in items if e.equipment_id == equipment_id]
    return items


@router.get("/limitations")
def limitations(loaded: EvidenceBundle = Depends(bundle)) -> dict:
    return {"limitations": loaded.limitations}


@router.get("/runs", response_model=list[RunRecord])
def runs(
    loaded: EvidenceBundle = Depends(bundle),
    kind: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    config: Settings = Depends(settings),
) -> list[RunRecord]:
    """Recorded runs. Read from the bundle in replay mode, from disk locally."""
    records = loaded.runs
    if kind:
        records = [r for r in records if r.kind == kind]
    return records[:limit]


@router.get("/runs/{run_id}", response_model=RunRecord)
def run_detail(
    run_id: str, loaded: EvidenceBundle = Depends(bundle), config: Settings = Depends(settings)
) -> RunRecord:
    for record in loaded.runs:
        if record.run_id == run_id:
            return record
    raise HTTPException(status_code=404, detail=f"no run record {run_id!r}")


@router.get("/reproducibility")
def reproducibility(loaded: EvidenceBundle = Depends(bundle)) -> dict:
    if loaded.reproducibility is None:
        return {"available": False, "note": "No repeat run has been compared against the original yet."}
    return {"available": True, "check": loaded.reproducibility.model_dump(mode="json")}
