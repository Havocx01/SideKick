"""The canonical in-memory dataset."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property

import numpy as np
import pandas as pd

from app.config import EXPERIMENT, ExperimentConfig
from app.schemas import ColumnMapping


class DatasetError(ValueError):
    pass


@dataclass
class Dataset:
    """Complete histories, sorted by equipment and cycle. Failure-cycle rows are unscorable."""

    frame: pd.DataFrame
    mapping: ColumnMapping
    dataset_id: str
    source: str
    data_hash: str
    config: ExperimentConfig = field(default=EXPERIMENT)

    @property
    def sensors(self) -> list[str]:
        return list(self.mapping.sensors)

    @cached_property
    def equipment_ids(self) -> list[str]:
        return [str(v) for v in pd.unique(self.frame["equipment_id"])]

    @cached_property
    def failure_cycles(self) -> dict[str, int]:
        first = self.frame.groupby("equipment_id", sort=False)["failure_cycle"].first()
        return {str(k): int(v) for k, v in first.items()}

    @cached_property
    def lifetimes(self) -> dict[str, int]:
        counts = self.frame.groupby("equipment_id", sort=False)["cycle"].size()
        return {str(k): int(v) for k, v in counts.items()}

    @cached_property
    def _row_slices(self) -> dict[str, tuple[int, int]]:
        """Sorted histories occupy contiguous blocks; cached slices avoid repeated frame scans."""
        ids = self.frame["equipment_id"].to_numpy()
        slices: dict[str, tuple[int, int]] = {}
        start = 0
        for index in range(1, len(ids) + 1):
            if index == len(ids) or ids[index] != ids[start]:
                slices[str(ids[start])] = (start, index)
                start = index
        return slices

    def rows_for(self, equipment_id: str) -> tuple[int, int]:
        try:
            return self._row_slices[str(equipment_id)]
        except KeyError as exc:
            raise DatasetError(f"unknown equipment id {equipment_id!r}") from exc

    def sensor_matrix(self, equipment_id: str) -> np.ndarray:
        start, stop = self.rows_for(equipment_id)
        return np.ascontiguousarray(self.frame.iloc[start:stop][self.sensors].to_numpy(dtype=float))

    def subset(self, equipment_ids: list[str]) -> Dataset:
        wanted = set(str(e) for e in equipment_ids)
        missing = wanted - set(self.equipment_ids)
        if missing:
            raise DatasetError(f"unknown equipment ids: {sorted(missing)}")
        mask = self.frame["equipment_id"].astype(str).isin(wanted).to_numpy()
        return Dataset(
            frame=self.frame.loc[mask].reset_index(drop=True),
            mapping=self.mapping,
            dataset_id=f"{self.dataset_id}#{len(wanted)}",
            source=self.source,
            data_hash=self.data_hash,
            config=self.config,
        )

    def label_vector(self) -> np.ndarray:
        """Failure-cycle rows get label zero and must be excluded with scorable_mask."""
        rul = self.frame["rul"].to_numpy(dtype=int)
        return ((rul >= 1) & (rul <= self.config.horizon_cycles)).astype(int)

    def scorable_mask(self) -> np.ndarray:
        """Exclude warm-up readings and the failure cycle."""
        warmup = self.config.feature_window - 1
        position = self.frame.groupby("equipment_id", sort=False).cumcount().to_numpy()
        rul = self.frame["rul"].to_numpy(dtype=int)
        mask = position >= warmup
        if self.config.exclude_failure_cycle:
            mask &= rul > 0
        return mask

    def describe(self) -> str:
        return (
            f"{self.dataset_id}: {len(self.equipment_ids)} engines, "
            f"{len(self.frame)} rows, {len(self.sensors)} channels"
        )
