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
