"""One local worker, with durable status, cancellation and a bounded lifetime."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

from app.config import get_settings
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

    def create(self, request: ExperimentCreate, *, library_owner="local") -> ExperimentRecord:
        with self.mutex:
            if self.stopping.is_set():
                raise ValueError("The server is shutting down. Retry after restarting it.")
            dataset = self.workspace.get("datasets", request.dataset_id)
            if not dataset["confirmed"]:
                raise ValueError("Confirm the dataset mapping and resolve its validation issues first.")
            from app.experiments.datasets import validated_dataset
            from app.experiments.protocol import check_coverage, protocol_config, resolve_protocol
            from app.schemas import ColumnMapping

            hosted = get_settings().mode == "demo"
            if hosted and (request.protocol is not None or request.pilot_brief is not None):
                raise ValueError("Custom protocols and pilot briefs are local only.")
            protocol = resolve_protocol(request, dataset)
            config = protocol_config(protocol, hosted=hosted)
            prepared = validated_dataset(
                self.workspace.directory("datasets", request.dataset_id) / "data.csv",
                ColumnMapping.model_validate(dataset["mapping"]), dataset["complete_histories"],
                id=request.dataset_id, source=dataset["source"], config=config,
            )
            check_coverage(prepared, protocol)
            pilot_brief = request.pilot_brief
            if dataset["source"] == "synthetic" and pilot_brief is not None:
                pilot_brief = pilot_brief.model_copy(update={"data_classification": "simulated"})
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
                pilot_brief=pilot_brief,
            )
            directory = self.workspace.directory("experiments", record.experiment_id)
            self.workspace.reserve(record.model_dump(mode="json"), library_owner=library_owner,
                                   folder_id=str(request.folder_id) if request.folder_id else None,
                                   folder_explicit="folder_id" in request.model_fields_set)
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

    def create_operation(self, experiment_id, kind, *, untouched_confirmed=False):
        from app.evidence.bundle import load_bundle
        from app.schemas import FrozenModelRecord, ValidationRecord

        with self.mutex:
            if get_settings().mode != "full":
                raise ValueError("Model freezing and final validation are local only.")
            if self.stopping.is_set():
                raise ValueError("The server is shutting down.")
            parent = self.workspace.get("experiments", experiment_id)
            if parent.get("job_kind", "development") != "development" or parent["status"] != "completed":
                raise ValueError("Complete the development experiment first.")
            loaded = load_bundle(self.workspace.directory("experiments", experiment_id) / "bundle.json")
            if loaded.schema_version < 3:
                raise ValueError("Start a new experiment before freezing a model. Historical bundles remain unchanged.")
            chosen = loaded.development_selection.recommended
            if chosen is None:
                raise ValueError("No candidate met the development criteria. There is no selected model to freeze.")
            if source_digest() != parent["source_digest"]:
                raise ValueError("Source changed after development. Start a new experiment with the current code.")
            frozen = self.workspace.operation(experiment_id, "freeze")
            if kind == "validation":
                if not untouched_confirmed:
                    raise ValueError("Explicitly confirm the reserved histories were not used for model or protocol decisions.")
                if not frozen or frozen["status"] != "completed":
                    raise ValueError("Freeze the selected model before final validation.")
            id, operation_id = str(uuid4()), str(uuid4())
            record = ExperimentRecord.model_validate({**parent, "experiment_id": id, "job_kind": kind,
                "parent_experiment_id": experiment_id, "operation_id": operation_id,
                "status": "queued", "created_at": time.time(), "started_at": None, "finished_at": None,
                "elapsed_seconds": 0, "stage": "queued", "completed_work": 0, "total_work": None,
                "work_unit": "", "error": None})
            if kind == "freeze":
                operation = FrozenModelRecord(freeze_id=operation_id, experiment_id=experiment_id, job_id=id,
                    candidate=f"{chosen.candidate.value}/{chosen.config_id}", created_at=time.time())
            else:
                operation = ValidationRecord(validation_id=operation_id, experiment_id=experiment_id,
                    freeze_id=frozen["freeze_id"], job_id=id, untouched_confirmed=True, created_at=time.time())
            self.workspace.reserve_operation(record.model_dump(mode="json"), operation.model_dump(mode="json"), kind)
            directory = self.workspace.directory("experiments", id)
            try:
                directory.mkdir(parents=True)
                self.thread = threading.Thread(target=self._run, args=(id,), daemon=True)
                self.thread.start()
            except (OSError, RuntimeError) as exc:
                self.workspace.update(id, status="failed", error=str(exc), finished_at=time.time())
                raise
            return operation

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
                        marker = "bundle.json" if self.workspace.get("experiments", id).get("job_kind", "development") == "development" else "result.json"
                        if code == 0 and (directory / marker).is_file():
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
        except Exception as exc:  # noqa: BLE001 - persist failures at the worker boundary
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
