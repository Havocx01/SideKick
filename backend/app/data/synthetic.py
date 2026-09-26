"""Deterministic synthetic run-to-failure histories."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.config import EXPERIMENT, ExperimentConfig
from app.data.contract import build_dataset
from app.data.dataset import Dataset
from app.schemas import ColumnMapping
from app.utils.determinism import rng

SYNTHETIC_SENSORS = (
    "temp_bearing",
    "vibration_rms",
    "pressure_out",
    "flow_rate",
    "current_draw",
    "speed_rpm",
    "oil_particles",
    "ambient_temp",
    "valve_position",
)
# Include a constant channel to exercise profiling and fault exclusion.
SYNTHETIC_CONSTANT = ("rated_voltage", "config_revision")


def make_synthetic_dataset(
    n_equipment: int = 60,
    *,
    min_life: int = 140,
    max_life: int = 300,
    noise: float = 0.35,
    seed: int | None = None,
    config: ExperimentConfig = EXPERIMENT,
) -> Dataset:
    baseSeed = seed if seed is not None else config.base_seed
    generator = rng(baseSeed, "synthetic", n_equipment, min_life, max_life)

    rows: list[pd.DataFrame] = []
    for index in range(n_equipment):
        unit = f"SYN-{index + 1:03d}"
        life = int(generator.integers(min_life, max_life + 1))
        cycles = np.arange(1, life + 1, dtype=np.int64)
        progress = cycles / life
        wear = float(generator.uniform(0.0, 0.3))

        frame = {"unit": unit, "cycle": cycles}
        for sensorIndex, sensor in enumerate(SYNTHETIC_SENSORS):
            direction = 1.0 if sensorIndex % 3 != 2 else -1.0
            scale = 1.0 + sensorIndex * 0.4
            sharpness = 2.0 + (sensorIndex % 4)
            signal = direction * scale * (wear + progress**sharpness) * 10.0
            level = 100.0 + sensorIndex * 25.0
            jitter = generator.normal(0.0, noise * scale, size=life)
            frame[sensor] = level + signal + jitter
        for constant in SYNTHETIC_CONSTANT:
            frame[constant] = 480.0 if constant == "rated_voltage" else 3.0
        rows.append(pd.DataFrame(frame))

    raw = pd.concat(rows, ignore_index=True)
    mapping = ColumnMapping(
        equipment_id="unit",
        cycle_index="cycle",
        sensors=[*SYNTHETIC_SENSORS, *SYNTHETIC_CONSTANT],
        failure_cycle=None,
        inferred=False,
    )
    return build_dataset(
        raw,
        mapping,
        dataset_id=f"synthetic-{n_equipment}",
        source="synthetic generator (not a benchmark result)",
        config=config,
    )
