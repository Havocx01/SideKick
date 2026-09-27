"""CSV mapping and validation for complete equipment histories."""

from __future__ import annotations

import hashlib
import json
import re

import numpy as np
import pandas as pd

from app.config import EXPERIMENT, ExperimentConfig
from app.data.dataset import Dataset, DatasetError
from app.schemas import ColumnMapping

CANONICAL_EQUIPMENT = "equipment_id"
CANONICAL_CYCLE = "cycle"
CANONICAL_FAILURE_CYCLE = "failure_cycle"
CANONICAL_RUL = "rul"
CANONICAL_COLUMNS = (CANONICAL_EQUIPMENT, CANONICAL_CYCLE, CANONICAL_FAILURE_CYCLE, CANONICAL_RUL)


class ContractError(DatasetError):
    pass


_EQUIPMENT_PATTERNS = (
    r"^equipment(_?id)?$",
    r"^unit(_?(number|id|nr))?$",
    r"^engine(_?(id|no|number))?$",
    r"^(machine|asset|device|pump|motor)(_?id)?$",
    r"^serial(_?number)?$",
)
_CYCLE_PATTERNS = (
    r"^cycle(_?(index|number|count))?$",
    r"^time(_?in_?cycles)?$",
    r"^(t|step|timestep|tick)$",
    r"^operating_?cycles?$",
)
_FAILURE_PATTERNS = (r"^failure(_?cycle)?$", r"^eol(_?cycle)?$", r"^end_?of_?life$", r"^cycle_?at_?failure$")
_RUL_PATTERNS = (r"^rul$", r"^remaining_?(useful_?)?life$", r"^cycles_?remaining$")

# Hours would require different warning windows; this version accepts cycles only.
_HOURS_PATTERNS = (r"hour", r"^hrs?$", r"runtime_?h", r"^elapsed_?time$")


def _matches(name: str, patterns: tuple[str, ...]) -> bool:
    key = name.strip().lower().replace(" ", "_").replace("-", "_")
    return any(re.search(p, key) for p in patterns)


def looks_like_hours(name: str) -> bool:
    return _matches(name, _HOURS_PATTERNS)


def infer_mapping(frame: pd.DataFrame) -> ColumnMapping:
    columns = list(frame.columns)
    if not columns:
        raise ContractError("the upload has no columns")

    equipmentCandidates = [c for c in columns if _matches(str(c), _EQUIPMENT_PATTERNS)]
    cycleCandidates = [c for c in columns if _matches(str(c), _CYCLE_PATTERNS)]
    failureCandidates = [c for c in columns if _matches(str(c), _FAILURE_PATTERNS)]
    rulCandidates = [c for c in columns if _matches(str(c), _RUL_PATTERNS)]

    ambiguous: list[str] = []

    # Equipment: fall back to a low-cardinality repeated column.
    if not equipmentCandidates:
        for column in columns:
            values = frame[column]
            unique = values.nunique(dropna=True)
            if 1 <= unique < max(2, len(frame) // 2) and unique < 10_000:
                equipmentCandidates = [column]
                ambiguous.append(str(column))
                break
    if not equipmentCandidates:
        raise ContractError(
            "no column identifies the piece of equipment. One column must hold a "
            "repeated identifier so histories can be separated."
        )
    if len(equipmentCandidates) > 1:
        ambiguous.extend(str(c) for c in equipmentCandidates[1:])
    equipment = equipmentCandidates[0]

    # Cycle: fall back to a column that increases within each equipment group.
    if not cycleCandidates:
        for column in columns:
            if column == equipment or not pd.api.types.is_numeric_dtype(frame[column]):
                continue
            grouped = frame.groupby(equipment, sort=False)[column]
            if bool(grouped.apply(lambda s: s.is_monotonic_increasing).all()):
                cycleCandidates = [column]
                ambiguous.append(str(column))
                break
    if not cycleCandidates:
        raise ContractError(
            "no column orders the readings. One column must hold an increasing cycle index per piece of equipment."
        )
    if len(cycleCandidates) > 1:
        ambiguous.extend(str(c) for c in cycleCandidates[1:])
    cycle = cycleCandidates[0]

    failure = failureCandidates[0] if failureCandidates else None
    reserved = {equipment, cycle, failure, *rulCandidates} - {None}

    sensors = [c for c in columns if c not in reserved and pd.api.types.is_numeric_dtype(frame[c])]
    ignored = [c for c in columns if c not in reserved and c not in sensors]

    if not sensors:
        raise ContractError("no numeric sensor columns were found")

    return ColumnMapping(
        equipment_id=str(equipment),
        cycle_index=str(cycle),
        sensors=[str(s) for s in sensors],
        failure_cycle=str(failure) if failure is not None else None,
        ignored=[str(c) for c in ignored],
        inferred=True,
        ambiguous=sorted(set(ambiguous)),
    )


def validate_mapping(frame: pd.DataFrame, mapping: ColumnMapping) -> None:
    missing = [
        name for name in [mapping.equipment_id, mapping.cycle_index, *mapping.sensors] if name not in frame.columns
    ]
    if mapping.failure_cycle and mapping.failure_cycle not in frame.columns:
        missing.append(mapping.failure_cycle)
    if missing:
        raise ContractError(f"columns not present in the upload: {missing}")

    if not pd.api.types.is_numeric_dtype(frame[mapping.cycle_index]):
        raise ContractError(f"cycle column {mapping.cycle_index!r} is not numeric")

    nonNumeric = [s for s in mapping.sensors if not pd.api.types.is_numeric_dtype(frame[s])]
    if nonNumeric:
        raise ContractError(f"sensor columns are not numeric: {nonNumeric}")

    roles = [mapping.equipment_id, mapping.cycle_index, *mapping.sensors]
    if mapping.failure_cycle:
        roles.append(mapping.failure_cycle)
    if len(set(roles)) != len(roles):
        raise ContractError("Columns assigned to two roles. Assign each column to exactly one role.")
    if not mapping.sensors:
        raise ContractError("Select at least one numeric sensor column.")
    if set(mapping.sensors) & set(CANONICAL_COLUMNS):
        raise ContractError("Rename sensor columns that use reserved names: equipment_id, cycle, failure_cycle, rul.")


def frame_hash(frame: pd.DataFrame, sensors: list[str], mapping: ColumnMapping | None = None) -> str:
    digest = hashlib.sha256()
    digest.update(b"sidekick-dataset-v2")
    if mapping is not None:
        digest.update(json.dumps(mapping.model_dump(), sort_keys=True).encode())
    digest.update("|".join(sensors).encode("utf-8"))
    digest.update(np.ascontiguousarray(frame[sensors].to_numpy(dtype=np.float64)).tobytes())
    digest.update(frame[CANONICAL_EQUIPMENT].astype(str).str.cat(sep="\x1f").encode("utf-8"))
    digest.update(np.ascontiguousarray(frame[CANONICAL_CYCLE].to_numpy(dtype=np.int64)).tobytes())
    if CANONICAL_FAILURE_CYCLE in frame:
        digest.update(np.ascontiguousarray(frame[CANONICAL_FAILURE_CYCLE].to_numpy(dtype=np.int64)).tobytes())
    return digest.hexdigest()[:16]


def build_dataset(
    frame: pd.DataFrame,
    mapping: ColumnMapping | None = None,
    *,
    dataset_id: str,
    source: str,
    config: ExperimentConfig = EXPERIMENT,
) -> Dataset:
    """The last reading is a failure target only when the caller confirms complete histories."""
    if mapping is None:
        mapping = infer_mapping(frame)
    validate_mapping(frame, mapping)

    renames = {mapping.equipment_id: CANONICAL_EQUIPMENT, mapping.cycle_index: CANONICAL_CYCLE}
    if mapping.failure_cycle:
        renames[mapping.failure_cycle] = CANONICAL_FAILURE_CYCLE

    keep = [mapping.equipment_id, mapping.cycle_index, *mapping.sensors]
    if mapping.failure_cycle:
        keep.append(mapping.failure_cycle)

    working = frame.loc[:, keep].rename(columns=renames).copy()
    if working[CANONICAL_EQUIPMENT].isna().any():
        raise ContractError("Equipment identifiers are missing. Fill in every equipment ID.")
    working[CANONICAL_EQUIPMENT] = working[CANONICAL_EQUIPMENT].astype(str)
    working[CANONICAL_CYCLE] = pd.to_numeric(working[CANONICAL_CYCLE], errors="coerce")

    if working[CANONICAL_CYCLE].isna().any():
        raise ContractError("the cycle column contains values that are not numbers")
    cycles = working[CANONICAL_CYCLE]
    if not np.isfinite(cycles).all() or (cycles % 1 != 0).any():
        raise ContractError("Cycle indices must be finite whole numbers. Correct fractional cycle values.")
    working[CANONICAL_CYCLE] = working[CANONICAL_CYCLE].astype(np.int64)

    for sensor in mapping.sensors:
        working[sensor] = pd.to_numeric(working[sensor], errors="coerce").astype(float)

    working = working.sort_values([CANONICAL_EQUIPMENT, CANONICAL_CYCLE], kind="mergesort")
    working = working.reset_index(drop=True)

    if CANONICAL_FAILURE_CYCLE in working.columns:
        failure = pd.to_numeric(working[CANONICAL_FAILURE_CYCLE], errors="coerce")
        if failure.isna().any():
            raise ContractError("the failure-cycle column contains missing values")
        if not np.isfinite(failure).all() or (failure % 1 != 0).any():
            raise ContractError("Failure cycles must be finite whole numbers.")
        working[CANONICAL_FAILURE_CYCLE] = failure.astype(np.int64)
        if (working.groupby(CANONICAL_EQUIPMENT)[CANONICAL_FAILURE_CYCLE].nunique() != 1).any():
            raise ContractError("Conflicting failure cycles. Use one failure cycle for each equipment history.")
    else:
        last = working.groupby(CANONICAL_EQUIPMENT, sort=False)[CANONICAL_CYCLE].transform("max")
        working[CANONICAL_FAILURE_CYCLE] = last.astype(np.int64)

    working[CANONICAL_RUL] = (working[CANONICAL_FAILURE_CYCLE] - working[CANONICAL_CYCLE]).astype(np.int64)

    if (working[CANONICAL_RUL] < 0).any():
        raise ContractError(
            "some readings are dated after their recorded failure cycle, so the failure cycle or the ordering is wrong"
        )

    ordered = [CANONICAL_EQUIPMENT, CANONICAL_CYCLE, *mapping.sensors, CANONICAL_FAILURE_CYCLE, CANONICAL_RUL]
    working = working.loc[:, ordered]

    return Dataset(
        frame=working,
        mapping=mapping,
        dataset_id=dataset_id,
        source=source,
        data_hash=frame_hash(working, list(mapping.sensors), mapping),
        config=config,
    )
