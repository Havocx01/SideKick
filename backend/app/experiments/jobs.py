"""One local worker, with durable status, cancellation and a bounded lifetime."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from app.config import EXPERIMENT, get_settings
from app.experiments.provenance import source_digest
from app.experiments.store import ACTIVE, Workspace
from app.schemas import ExperimentCreate, ExperimentRecord


class Jobs:
    def __init__(self, root: Path, *, timeout_seconds: float = 900):
        self.workspace = Workspace(root)
        # An OS lock prevents a second local server from interrupting the first.
        self.lock_file = (self.workspace.root / "server.lock").open("a+b")
        self.lock_file.seek(0)
        self.lock_file.write(b"0")
        self.lock_file.flush()
        self.lock_file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock_file.close()
            raise RuntimeError(
                "Another Sidekick server owns this local workspace. Stop it or choose another artifacts directory."
            ) from None
        self.workspace.recover()
        self.timeout_seconds = timeout_seconds
        self.stopping = threading.Event()
        self.mutex = threading.Lock()
        self.thread: threading.Thread | None = None

    def create(self, request: ExperimentCreate) -> ExperimentRecord:
        with self.mutex:
            if self.stopping.is_set():
                raise ValueError("The server is shutting down. Retry after restarting it.")
            dataset = self.workspace.get("datasets", request.dataset_id)
            if not dataset["confirmed"]:
                raise ValueError("Confirm the dataset mapping and resolve its validation issues first.")
            config = replace(
                EXPERIMENT,
                protocol_revision=3,
                min_detection_fraction=request.min_detection_fraction,
                max_early_alarm_burden=request.max_early_alarm_burden,
                configs_per_candidate=1 if get_settings().mode == "demo" else EXPERIMENT.configs_per_candidate,
            )
            record = ExperimentRecord(
                experiment_id=str(uuid4()),
                dataset_id=request.dataset_id,
                name=dataset["name"],
                source=dataset["source"],
                status="queued",
                created_at=time.time(),
                config=config.as_dict(),
                config_fingerprint=config.fingerprint(),
                data_hash=dataset["profile"]["data_hash"],
                source_digest=source_digest(),
            )
            directory = self.workspace.directory("experiments", record.experiment_id)
            self.workspace.reserve(record.model_dump(mode="json"))
            try:
                directory.mkdir(parents=True)
                self.thread = threading.Thread(target=self._run, args=(record.experiment_id,), daemon=True)
                self.thread.start()
            except (OSError, RuntimeError) as exc:
                self.workspace.update(record.experiment_id, status="failed", error=str(exc), finished_at=time.time())
                raise
            return record

    def cancel(self, id: str):
        record = self.workspace.get("experiments", id)
        if record["status"] in ACTIVE:
            self.workspace.update(id, status="cancelling")

    def _run(self, id: str):
        process = None
        directory = self.workspace.directory("experiments", id)
        started = time.time()
        try:
            # A cancellation between reservation and process launch is still honoured.
            if not self.workspace.update(
                id, expected_status=("queued",), status="running", started_at=started, stage="validating"
            ):
                self.workspace.update(id, status="cancelled", finished_at=time.time())
                return
            env = dict(os.environ)
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
            env["SIDEKICK_MLFLOW"] = "0"
            if env.get("SIDEKICK_MODE") == "demo":
                env["SIDEKICK_TRAIN_THREADS"] = "1"
            # The worker never needs external services or their credentials.
            env.pop("OPENAI_API_KEY", None)
            for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
                env[key] = "1"
            with (directory / "worker.log").open("wb") as log:
                process = subprocess.Popen(
                    [sys.executable, "-m", "app.experiments.worker", str(self.workspace.root), id],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                while True:
                    status = self.workspace.get("experiments", id)["status"]
                    terminal = None
                    error = None
                    if self.stopping.is_set():
                        terminal, error = "interrupted", "The server stopped. Start a new run using this dataset."
                    elif status == "cancelling":
                        terminal = "cancelled"
                    elif time.time() - started >= self.timeout_seconds:
                        terminal, error = (
                            "timed_out",
                            "This experiment reached the 15-minute limit. Try fewer sensor columns or smaller histories.",
                        )
                    if terminal:
                        self._stop(process)
                        self.workspace.update(id, status=terminal, error=error, finished_at=time.time())
                        break
                    code = process.poll()
                    if code is not None:
                        if code == 0 and (directory / "bundle.json").is_file():
                            saved = self.workspace.update(
                                id,
                                expected_status=("running",),
                                status="completed",
                                stage="results ready",
                                finished_at=time.time(),
                            )
                            if not saved:
                                self.workspace.update(id, status="cancelled", finished_at=time.time())
                        else:
                            errorPath = directory / "error.txt"
                            message = (
                                errorPath.read_text(encoding="utf-8")
                                if errorPath.exists()
                                else "The worker stopped unexpectedly. See its local worker.log and start a new run."
                            )
                            self.workspace.update(id, status="failed", error=message, finished_at=time.time())
                        break
                    self.workspace.heartbeat(id)
                    self.stopping.wait(0.25)
        except Exception as exc:
            if process is not None:
                self._stop(process)
            self.workspace.update(id, status="failed", error=str(exc), finished_at=time.time())

    @staticmethod
    def _stop(process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)

    def close(self):
        with self.mutex:
            self.stopping.set()
        if self.thread:
            self.thread.join(timeout=8)
        self.lock_file.close()
