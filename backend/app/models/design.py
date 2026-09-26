"""Assembling design matrices from a dataset and a feature builder."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.data.contract import CANONICAL_CYCLE, CANONICAL_RUL
from app.data.dataset import Dataset
from app.features.build import FeatureBuilder
from app.models.base import DesignMatrix


@dataclass
class EngineBlock:
    equipment_id: str
    features: np.ndarray
    labels: np.ndarray
    cycles: np.ndarray
    rul: np.ndarray
    rows: np.ndarray
    scorable: np.ndarray

    @property
    def n_scorable(self) -> int:
        return int(self.scorable.sum())


def engine_blocks(
    dataset: Dataset, builder: FeatureBuilder, *, equipment_ids: list[str] | None = None
) -> dict[str, EngineBlock]:
    labels = dataset.label_vector()
    scorable = dataset.scorable_mask()
    targets = equipment_ids if equipment_ids is not None else dataset.equipment_ids

    blocks: dict[str, EngineBlock] = {}
    for equipmentId in targets:
        start, stop = dataset.rows_for(equipmentId)
        frame = dataset.frame.iloc[start:stop]
        blocks[equipmentId] = EngineBlock(
            equipment_id=equipmentId,
            features=builder.build_engine(dataset.sensor_matrix(equipmentId)),
            labels=labels[start:stop],
            cycles=frame[CANONICAL_CYCLE].to_numpy(dtype=int),
            rul=frame[CANONICAL_RUL].to_numpy(dtype=int),
            rows=np.arange(start, stop),
            scorable=scorable[start:stop],
        )
    return blocks


def design_from_blocks(
    blocks: dict[str, EngineBlock],
    feature_names: list[str],
    *,
    equipment_ids: list[str] | None = None,
    scorable_only: bool = True,
) -> DesignMatrix:
    targets = equipment_ids if equipment_ids is not None else list(blocks)
    selected = [blocks[e] for e in targets]
    if not selected:
        raise ValueError("no engines selected for the design matrix")

    def stack(getter, dtype):
        parts = [(getter(b)[b.scorable] if scorable_only else getter(b)) for b in selected]
        return np.concatenate(parts).astype(dtype, copy=False)

    features = np.vstack([(b.features[b.scorable] if scorable_only else b.features) for b in selected])
    equipment = np.concatenate(
        [np.full(b.n_scorable if scorable_only else len(b.rul), b.equipment_id, dtype=object) for b in selected]
    )

    return DesignMatrix(
        X=features,
        y=stack(lambda b: b.labels, np.int64),
        cycle=stack(lambda b: b.cycles, np.int64),
        equipment_id=equipment.astype(str),
        rul=stack(lambda b: b.rul, np.int64),
        rows=stack(lambda b: b.rows, np.int64),
        feature_names=list(feature_names),
    )


def build_design(dataset: Dataset, builder: FeatureBuilder, *, equipment_ids: list[str] | None = None) -> DesignMatrix:
    blocks = engine_blocks(dataset, builder, equipment_ids=equipment_ids)
    return design_from_blocks(blocks, builder.feature_names(), equipment_ids=equipment_ids)


def assert_engine_disjoint(train: DesignMatrix, validation: DesignMatrix) -> None:
    overlap = set(np.unique(train.equipment_id)) & set(np.unique(validation.equipment_id))
    if overlap:
        raise AssertionError(f"engines appear in both training and validation: {sorted(overlap)}")
