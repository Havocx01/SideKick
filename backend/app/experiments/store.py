"""Transactional local metadata. Dataset files become immutable on confirmation."""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

ACTIVE = ("queued", "running", "cancelling")


def identifier(value: str) -> str:
    return str(UUID(value))


class Workspace:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "workspace.sqlite3"
        with self.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS datasets (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS experiments (
                    id TEXT PRIMARY KEY, status TEXT NOT NULL, payload TEXT NOT NULL,
                    heartbeat REAL NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_experiment ON experiments ((1))
                    WHERE status IN ('queued','running','cancelling');
                CREATE TABLE IF NOT EXISTS operations (
                    id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL, kind TEXT NOT NULL,
                    payload TEXT NOT NULL, UNIQUE(experiment_id, kind));
                CREATE TABLE IF NOT EXISTS exposures (
                    history_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL,
                    reason TEXT NOT NULL, exposed_at REAL NOT NULL);
            """)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db, timeout=15)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def directory(self, kind: str, id: str) -> Path:
        if kind not in ("datasets", "experiments"):
            raise ValueError("Unknown record type")
        return self.root / kind / identifier(id)

    def get(self, kind: str, id: str) -> dict:
        self.directory(kind, id)
        with self.connect() as conn:
            row = conn.execute(f"SELECT payload FROM {kind} WHERE id=?", (id,)).fetchone()
        if row is None:
            raise KeyError(id)
        return json.loads(row[0])

    def save_dataset(self, record: dict):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            old = conn.execute("SELECT payload FROM datasets WHERE id=?", (record["dataset_id"],)).fetchone()
            if old and json.loads(old[0])["confirmed"]:
                raise ValueError("This dataset is already confirmed. Upload another copy to change its mapping.")
            conn.execute(
                "INSERT OR REPLACE INTO datasets VALUES (?,?)",
                (record["dataset_id"], json.dumps(record, allow_nan=False)),
            )

    def reserve(self, record: dict):
        try:
            with self.connect() as conn:
                conn.execute(
                    "INSERT INTO experiments VALUES (?,?,?,?)",
                    (record["experiment_id"], record["status"], json.dumps(record), time.time()),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                "The server is already running an experiment. Try again when it finishes, or explore the recorded benchmark."
            ) from exc

    def reserve_operation(self, record, operation, kind):
        try:
            with self.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                old = conn.execute("SELECT id,payload FROM operations WHERE experiment_id=? AND kind=?", (record["parent_experiment_id"], kind)).fetchone()
                if old:
                    previous = json.loads(old[1])
                    job = conn.execute("SELECT status FROM experiments WHERE id=?", (previous["job_id"],)).fetchone()
                    if job and job[0] in ("failed", "cancelled", "timed_out", "interrupted") and not previous.get("exposure_started_at"):
                        conn.execute("DELETE FROM operations WHERE id=?", (old[0],))
                conn.execute("INSERT INTO experiments VALUES (?,?,?,?)", (record["experiment_id"], record["status"], json.dumps(record), time.time()))
                conn.execute("INSERT INTO operations VALUES (?,?,?,?)", (record["operation_id"], record["parent_experiment_id"], kind, json.dumps(operation)))
        except sqlite3.IntegrityError as exc:
            raise ValueError("This operation already exists, or another local job is active.") from exc

    def operation(self, experiment_id, kind):
        identifier(experiment_id)
        with self.connect() as conn:
            row = conn.execute("SELECT payload FROM operations WHERE experiment_id=? AND kind=?", (experiment_id, kind)).fetchone()
        if row is None:
            return None
        record = json.loads(row[0])
        job = self.get("experiments", record["job_id"])
        record["status"] = job["status"]
        record["error"] = job.get("error")
        return record

    def update_operation(self, operation_id, **changes):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT payload FROM operations WHERE id=?", (operation_id,)).fetchone()
            if row is None:
                raise KeyError(operation_id)
            record = json.loads(row[0])
            record.update(changes)
            conn.execute("UPDATE operations SET payload=? WHERE id=?", (json.dumps(record, allow_nan=False), operation_id))

    def expose(self, histories, experiment_id, reason, *, validation_id=None):
        histories = list(histories)
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if validation_id:
                for history in histories:
                    if conn.execute("SELECT 1 FROM exposures WHERE history_id=?", (history,)).fetchone():
                        raise ValueError("Reserved equipment has already been used or scored. Use genuinely fresh histories.")
                row = conn.execute("SELECT payload FROM operations WHERE id=?", (validation_id,)).fetchone()
                operation = json.loads(row[0])
                if operation.get("exposure_started_at") is not None:
                    raise ValueError("This validation attempt has already started scoring.")
                operation["exposure_started_at"] = time.time()
                conn.execute("UPDATE operations SET payload=? WHERE id=?", (json.dumps(operation), validation_id))
            conn.executemany("INSERT OR IGNORE INTO exposures VALUES (?,?,?,?)", [(h, experiment_id, reason, time.time()) for h in histories])

    def exposed(self, histories):
        with self.connect() as conn:
            return [h for h in histories if conn.execute("SELECT 1 FROM exposures WHERE history_id=?", (h,)).fetchone()]

    def update(self, id: str, *, active_only: bool = True, expected_status=None, **changes):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT payload, status FROM experiments WHERE id=?", (id,)).fetchone()
            if not row or (active_only and row[1] not in ACTIVE):
                return False
            if expected_status is not None and row[1] not in expected_status:
                return False
            record = json.loads(row[0])
            record.update(changes)
            conn.execute(
                "UPDATE experiments SET payload=?, status=? WHERE id=?", (json.dumps(record), record["status"], id)
            )
            return True

    def heartbeat(self, id: str):
        with self.connect() as conn:
            conn.execute("UPDATE experiments SET heartbeat=? WHERE id=?", (time.time(), id))

    def alive(self, id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT status,heartbeat FROM experiments WHERE id=?", (id,)).fetchone()
        return bool(row and row[0] in ("queued", "running") and time.time() - row[1] < 12)

    def list(self) -> list[dict]:
        with self.connect() as conn:
            records = [json.loads(row[0]) for row in conn.execute("SELECT payload FROM experiments")]
        for record in records:
            start = record["started_at"] or record["created_at"]
            record["elapsed_seconds"] = max(0, (record["finished_at"] or time.time()) - start)
        return sorted(records, key=lambda record: record["created_at"], reverse=True)

    def recover(self):
        for record in self.list():
            if record["status"] in ACTIVE:
                self.update(
                    record["experiment_id"],
                    status="interrupted",
                    finished_at=time.time(),
                    error="The server stopped before this experiment finished. Start a new run using this dataset.",
                )
