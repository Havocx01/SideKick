"""CSV preparation for local uploads and synthetic experiments."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from app.config import EXPERIMENT
from app.data.contract import build_dataset, infer_mapping, validate_mapping
from app.data.profiler import profile_dataset
from app.data.synthetic import make_synthetic_dataset
from app.models.splits import make_splits
from app.schemas import ColumnMapping, DatasetConfirmation, DatasetRegistration

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def read_csv(path: Path, equipment_column: str | None = None) -> pd.DataFrame:
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            header = next(csv.reader(stream), [])
    except csv.Error as exc:
        raise ValueError("The CSV header cannot be read. Use short column names separated by commas.") from exc
    if not header or len(set(header)) != len(header) or any(not c.strip() for c in header):
        raise ValueError("CSV column names must be present and unique. Rename duplicate or empty headers.")
    if len(header) > 128:
        raise ValueError("Use at most 128 columns for this local prototype.")
    frame = pd.read_csv(path, dtype={equipment_column: "string"} if equipment_column else None)
    if frame.empty:
        raise ValueError("The CSV has no readings. Include a header and equipment histories.")
    return frame


def register(workspace, path: Path, id: str, name: str, source="upload", *, library_owner="local", folder_id=None) -> DatasetRegistration:
    frame = read_csv(path)
    try:
        mapping = infer_mapping(frame)
    except ValueError:
        mapping = None
    record = DatasetRegistration(
        dataset_id=id,
        name=name[:120],
        source=source,
        columns=list(frame.columns),
        preview=json.loads(frame.head(8).to_json(orient="records")),
        row_count=len(frame),
        mapping=mapping,
    )
    workspace.save_dataset(record.model_dump(mode="json"), library_owner=library_owner, folder_id=folder_id)
    return record


def validated_dataset(path, mapping, complete_histories, *, id, source, config=EXPERIMENT):
    frame = read_csv(path, mapping.equipment_id)
    validate_mapping(frame, mapping)
    if not mapping.failure_cycle and not complete_histories:
        raise ValueError(
            "Confirm that every history reaches failure, or supply a failure-cycle column. The final reading is never assumed to be failure without confirmation."
        )
    if frame[mapping.equipment_id].astype(str).str.strip().eq("").any():
        raise ValueError("Equipment IDs cannot be empty. Fill in every identifier.")
    if frame.duplicated([mapping.equipment_id, mapping.cycle_index]).any():
        raise ValueError("Duplicate equipment/cycle pairs. Keep exactly one reading per cycle for each equipment ID.")
    if np.isinf(frame[mapping.sensors].to_numpy(dtype=float)).any():
        raise ValueError("Sensors contain infinity. Correct those values or mark missing readings with an empty cell.")
    dataset = build_dataset(frame, mapping, dataset_id=id, source=source, config=config)
    last = dataset.frame.groupby("equipment_id")["cycle"].max().to_dict()
    if any(last[e] != failure for e, failure in dataset.failure_cycles.items()):
        raise ValueError(
            "Censored histories are unsupported: each history must include its known failure cycle. Supply complete histories; do not label the last reading as failure unless it really failed."
        )
    from app.experiments.preflight import validate_histories
    validate_histories(dataset)
    profile = profile_dataset(dataset, config=config)
    if not profile.usable:
        raise ValueError(" ".join(f.message for f in profile.findings if f.severity.value == "blocker"))
    make_splits(dataset, config)
    return dataset


def confirm(workspace, id: str, request: DatasetConfirmation) -> DatasetRegistration:
    record = DatasetRegistration.model_validate(workspace.get("datasets", id))
    mapping = request.mapping.model_copy(update={"inferred": False, "ambiguous": []})
    dataset = validated_dataset(
        workspace.directory("datasets", id) / "data.csv",
        mapping,
        request.complete_histories,
        id=id,
        source=record.source,
    )
    record.mapping = mapping
    record.complete_histories = request.complete_histories
    record.profile = profile_dataset(dataset)
    record.splits = make_splits(dataset)
    record.confirmed = True
    workspace.save_dataset(record.model_dump(mode="json"))
    return record


def sample(workspace, *, hosted: bool = False, library_owner="local") -> DatasetRegistration:
    id = str(uuid4())
    directory = workspace.directory("datasets", id)
    directory.mkdir(parents=True)
    dataset = make_synthetic_dataset(n_equipment=30, min_life=100, max_life=160) if hosted else make_synthetic_dataset()
    sensors = dataset.sensors[:3] if hosted else dataset.sensors
    path = directory / "data.csv"
    dataset.frame[["equipment_id", "cycle", *sensors, "failure_cycle"]].to_csv(path, index=False)
    name = "Hosted sample: 30 histories, 3 sensors" if hosted else "Synthetic equipment sample"
    register(workspace, path, id, name, "synthetic", library_owner=library_owner)
    return confirm(
        workspace,
        id,
        DatasetConfirmation(
            mapping=ColumnMapping(
                equipment_id="equipment_id", cycle_index="cycle", sensors=sensors, failure_cycle="failure_cycle"
            ),
            complete_histories=True,
        ),
    )
