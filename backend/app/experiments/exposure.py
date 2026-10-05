"""Recognize reused histories without treating new names or labels as fresh data."""

import hashlib
import json

import numpy as np


def history_ids(dataset, equipment):
    result = {}
    for identifier in equipment:
        frame = dataset.frame[dataset.frame["equipment_id"] == identifier].sort_values("cycle")
        cycle = np.ascontiguousarray(frame["cycle"].to_numpy(dtype="<i8"))
        channels = []
        for sensor in dataset.sensors:
            values = frame[sensor].to_numpy(dtype="<f8", copy=True)
            values[np.isnan(values)] = np.nan
            values[values == 0] = 0
            channels.append(hashlib.sha256(values.tobytes()).digest())
        digest = hashlib.sha256(b"sidekick-history-v1" + cycle.tobytes() + b"".join(sorted(channels)))
        result[identifier] = digest.hexdigest()
    return result


def seed_known_exposure(workspace):
    """Recorded benchmark and legacy local development records cannot become fresh."""
    from app.config import ExperimentConfig, get_settings
    from app.data.loader import load_dataset
    from app.experiments.datasets import validated_dataset
    from app.schemas import ColumnMapping

    with workspace.connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        if conn.execute("SELECT 1 FROM metadata WHERE key='exposure_seed_v1.5'").fetchone():
            return

    path = get_settings().bundle_path
    if path.is_file():
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        if raw.get("profile", {}).get("dataset_id") == "cmapss-fd001-train":
            # Both development and historical holdout FD001 histories were examined.
            identities = path.parent / "history-identities.json"
            if identities.is_file():
                known = json.loads(identities.read_text(encoding="utf-8"))
                workspace.expose(known["histories"].values(), "benchmark", "Previously examined NASA FD001 histories")
            elif (get_settings().cmapss_dir / "train_FD001.txt").is_file():
                data = load_dataset("cmapss", subset="FD001")
                ids = raw["splits"]["development"] + raw["splits"]["holdout"]
                workspace.expose(history_ids(data, ids).values(), "benchmark", "Previously examined NASA FD001 histories")
            else:
                raise ValueError("Known NASA exposure identities are unavailable. Restore evidence/history-identities.json before final validation.")
    for record in workspace.list():
        if record.get("job_kind", "development") != "development":
            continue
        legacy_incomplete = (record.get("config", {}).get("protocol_revision", 1) < 4
            and record.get("started_at") and record["status"] != "completed")
        if record["status"] != "completed" and not legacy_incomplete:
            continue
        registration = workspace.get("datasets", record["dataset_id"])
        data = validated_dataset(workspace.directory("datasets", record["dataset_id"]) / "data.csv",
                                 ColumnMapping.model_validate(registration["mapping"]), registration["complete_histories"],
                                 id=record["dataset_id"], source=record["source"], config=ExperimentConfig(**record["config"]))
        bundle_path = workspace.directory("experiments", record["experiment_id"]) / "bundle.json"
        if legacy_incomplete:
            workspace.expose(history_ids(data, data.equipment_ids).values(), record["experiment_id"],
                "Prior incomplete legacy run; fresh status cannot be established")
            continue
        raw = json.loads(bundle_path.read_text(encoding="utf-8"))
        ids = raw["splits"]["development"]
        if raw.get("final_evaluation") is not None:
            ids += raw["splits"]["holdout"]
        workspace.expose(history_ids(data, ids).values(), record["experiment_id"], "Previously used development or final-validation history")
    with workspace.connect() as conn:
        conn.execute("INSERT OR IGNORE INTO metadata VALUES ('exposure_seed_v1.5','complete')")
