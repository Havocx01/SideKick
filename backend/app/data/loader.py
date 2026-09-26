"""Readers for the benchmark, for uploaded CSVs and for synthetic histories."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.config import EXPERIMENT, ExperimentConfig, get_settings
from app.data.contract import ContractError, build_dataset, infer_mapping
from app.data.dataset import Dataset, DatasetError
from app.schemas import ColumnMapping

CMAPSS_SUBSETS = ("FD001", "FD002", "FD003", "FD004")

CMAPSS_OP_SETTINGS = tuple(f"op_setting_{i}" for i in range(1, 4))
CMAPSS_SENSORS = tuple(f"sensor_{i}" for i in range(1, 22))
CMAPSS_COLUMNS = ("unit", "cycle", *CMAPSS_OP_SETTINGS, *CMAPSS_SENSORS)


def cmapss_train_path(subset: str = "FD001", data_dir: Path | None = None) -> Path:
    if subset not in CMAPSS_SUBSETS:
        raise ValueError(f"unknown C-MAPSS subset {subset!r}; expected one of {CMAPSS_SUBSETS}")
    base = data_dir or get_settings().cmapss_dir
    return Path(base) / f"train_{subset}.txt"


def read_cmapss_file(path: Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise DatasetError(
            f"{path} not found. Run 'python scripts/fetch_data.py' to download the "
            f"C-MAPSS archive, or pass --synthetic to work without it."
        )
    frame = pd.read_csv(path, sep=r"\s+", header=None, engine="python")
    if frame.shape[1] < len(CMAPSS_COLUMNS):
        raise DatasetError(f"{path.name} has {frame.shape[1]} columns; the C-MAPSS format has {len(CMAPSS_COLUMNS)}")
    # Some distributions carry trailing all-empty columns from the fixed-width export.
    frame = frame.iloc[:, : len(CMAPSS_COLUMNS)]
    frame.columns = list(CMAPSS_COLUMNS)
    return frame


def load_cmapss(
    subset: str = "FD001", *, data_dir: Path | None = None, config: ExperimentConfig = EXPERIMENT
) -> Dataset:
    """Only training histories are complete; the censored test file is unsupported."""
    path = cmapss_train_path(subset, data_dir)
    raw = read_cmapss_file(path)
    mapping = ColumnMapping(
        equipment_id="unit",
        cycle_index="cycle",
        sensors=[*CMAPSS_OP_SETTINGS, *CMAPSS_SENSORS],
        failure_cycle=None,
        inferred=False,
    )
    return build_dataset(
        raw,
        mapping,
        dataset_id=f"cmapss-{subset.lower()}-train",
        source=f"NASA C-MAPSS {subset} training file ({path.name})",
        config=config,
    )


def load_csv(path: Path, mapping: ColumnMapping | None = None, *, config: ExperimentConfig = EXPERIMENT) -> Dataset:
    path = Path(path)
    if not path.exists():
        raise DatasetError(f"{path} not found")
    frame = pd.read_csv(path)
    if frame.empty:
        raise ContractError("the uploaded file has no rows")
    if mapping is None:
        mapping = infer_mapping(frame)
    return build_dataset(
        frame, mapping, dataset_id=f"upload-{path.stem}", source=f"uploaded file {path.name}", config=config
    )


def load_dataset(
    source: str = "cmapss", *, subset: str = "FD001", path: Path | None = None, config: ExperimentConfig = EXPERIMENT
) -> Dataset:
    if source == "cmapss":
        return load_cmapss(subset, config=config)
    if source == "synthetic":
        from app.data.synthetic import make_synthetic_dataset

        return make_synthetic_dataset(config=config)
    if source == "csv":
        if path is None:
            raise ValueError("source='csv' requires a path")
        return load_csv(path, config=config)
    raise ValueError(f"unknown dataset source {source!r}")
