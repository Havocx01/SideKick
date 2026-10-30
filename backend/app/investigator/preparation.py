import logging
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from uuid import uuid4

from app.experiments.provenance import source_digest
from app.experiments.validation import dependency_versions
from app.faults.replay import ReplayManifest, load_trusted_context, read_json
from app.investigator.schemas import ContextPreparation, ContextPreparationState
from app.investigator.preparation_worker import MAX_SECONDS, PARENT_TIMEOUT, STAGES


class PreparationBusy(RuntimeError):
    pass


class ContextPreparer:
    def __init__(self, root, store, *, timeout=MAX_SECONDS):
        self.root = root
        self.store = store
        self.timeout = timeout
        self.thread = None
        self.stopping = threading.Event()
        self.lock = threading.Lock()
        self.recoveryUntil = 0
        with store.transaction() as db:
            db.execute("CREATE TABLE IF NOT EXISTS context_preparations(id TEXT PRIMARY KEY, owner TEXT NOT NULL, request_id TEXT NOT NULL,"
                " status TEXT NOT NULL, payload TEXT NOT NULL, created REAL NOT NULL, UNIQUE(owner,request_id))")
            for id, payload in db.execute("SELECT id,payload FROM context_preparations WHERE status IN ('queued','running','cancelling','interrupted')").fetchall():
                heartbeat = root / "preparations" / id / "heartbeat"
                if heartbeat.is_file():
                    self.recoveryUntil = max(self.recoveryUntil, heartbeat.stat().st_mtime + PARENT_TIMEOUT + 1)
                job = ContextPreparation.model_validate_json(payload).model_copy(update={"status": "interrupted",
                    "error": "Preparation stopped when the server restarted. Prepare a new sample to continue."})
                name = f"synthetic-{id[:12]}"
                if (root / "contexts" / name / "manifest.json").is_file():
                    try:
                        load_trusted_context(root / "contexts" / name, trusted=True)
                        job = job.model_copy(update={"status": "completed", "stage": "ready", "context": name, "error": None})
                    except (ValueError, OSError):
                        pass
                db.execute("UPDATE context_preparations SET status=?,payload=? WHERE id=?", (job.status, job.model_dump_json(), id))

    def get(self, owner, id):
        with self.store.connection() as db:
            row = db.execute("SELECT payload FROM context_preparations WHERE owner=? AND id=?", (owner, id)).fetchone()
        if row is None:
            raise KeyError("Unknown preparation")
        return ContextPreparation.model_validate_json(row[0])

    def state(self, owner):
        with self.store.connection() as db:
            row = db.execute("SELECT payload FROM context_preparations WHERE owner=? ORDER BY created DESC LIMIT 1", (owner,)).fetchone()
        outdated = 0
        digest, versions = source_digest(), dependency_versions()
        for path in (self.root / "contexts").glob("*/manifest.json"):
            try:
                manifest = ReplayManifest.model_validate(read_json(path))
                outdated += int(manifest.source_digest != digest or manifest.dependency_versions != versions)
            except (ValueError, OSError):
                outdated += 1
        return ContextPreparationState(job=ContextPreparation.model_validate_json(row[0]) if row else None, outdated=outdated)

    def start(self, owner, request):
        with self.lock:
            with self.store.transaction() as db:
                if self.stopping.is_set():
                    raise PreparationBusy("The workspace is stopping. Restart it before preparing a model.")
                row = db.execute("SELECT payload FROM context_preparations WHERE owner=? AND request_id=?", (owner, request.requestId)).fetchone()
                if row:
                    return ContextPreparation.model_validate_json(row[0])
                if time.time() < self.recoveryUntil:
                    raise PreparationBusy("The previous preparation worker is stopping after a restart. Wait a few seconds, then try again.")
                if db.execute("SELECT 1 FROM context_preparations WHERE status IN ('queued','running','cancelling')").fetchone():
                    raise PreparationBusy("Another model setup is being prepared. Wait for it to finish.")
                job = ContextPreparation(id=uuid4().hex, status="queued", stage="queued", createdAt=time.time())
                db.execute("INSERT INTO context_preparations VALUES(?,?,?,?,?,?)", (job.id, owner, request.requestId, job.status, job.model_dump_json(), job.createdAt))
            self.thread = threading.Thread(target=self.work, args=(owner, job.id), daemon=True, name="prepare-investigation")
            self.thread.start()
        return job

    def update(self, owner, id, **changes):
        with self.store.transaction() as db:
            row = db.execute("SELECT payload FROM context_preparations WHERE owner=? AND id=?", (owner, id)).fetchone()
            job = ContextPreparation.model_validate_json(row[0])
            if job.status not in {"queued", "running", "cancelling"}:
                return job
            if job.status == "cancelling" and changes.get("status") in {"queued", "running"}:
                return job
            job = ContextPreparation.model_validate({**job.model_dump(), **changes})
            db.execute("UPDATE context_preparations SET status=?,payload=? WHERE id=?", (job.status, job.model_dump_json(), id))
        return job

    def cancel(self, owner, id):
        self.get(owner, id)
        return self.update(owner, id, status="cancelling", error="Stopping preparation. Your saved models and investigations are unchanged.")

    def work(self, owner, id):
        process = None
        terminal = None
        directory = self.root / "preparations" / id
        try:
            if self.update(owner, id, status="running").status != "running":
                terminal = {"status": "cancelled", "error": "Preparation cancelled. Your saved models and investigations are unchanged."}
                return
            directory.mkdir(parents=True, exist_ok=False)
            heartbeat = directory / "heartbeat"
            heartbeat.touch()
            env = dict(os.environ)
            env.update(PYTHONPATH=str(Path(__file__).resolve().parents[2]), SIDEKICK_MLFLOW="0", SIDEKICK_TRAIN_THREADS="1")
            for key in ("OPENAI_API_KEY", "NEBIUS_API_KEY", "TAVILY_API_KEY"):
                env.pop(key, None)
            for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
                env[key] = "1"
            started = time.monotonic()
            with (directory / "worker.log").open("wb") as log:
                process = subprocess.Popen([sys.executable, "-m", "app.investigator.preparation_worker", str(directory)],
                    env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                while True:
                    if self.stopping.is_set():
                        terminal = {"status": "interrupted", "error": "Preparation stopped with the server. Prepare a new sample to continue."}
                        return
                    if self.get(owner, id).status == "cancelling":
                        terminal = {"status": "cancelled", "error": "Preparation cancelled. Your saved models and investigations are unchanged."}
                        return
                    if time.monotonic() - started >= self.timeout:
                        terminal = {"status": "failed", "error": "Preparation reached its time limit. Try again when the workspace is less busy."}
                        return
                    heartbeat.touch()
                    for stage in reversed(STAGES):
                        if (directory / f"stage-{stage}").is_file():
                            self.update(owner, id, stage=stage)
                            break
                    code = process.poll()
                    if code is not None:
                        if code != 0:
                            raise RuntimeError("The preparation worker failed")
                        break
                    self.stopping.wait(.1)
            package = directory / "context"
            load_trusted_context(package, trusted=True)
            name = f"synthetic-{id[:12]}"
            with self.store.transaction() as db:
                row = db.execute("SELECT status FROM context_preparations WHERE id=?", (id,)).fetchone()
                if row[0] != "running" or self.stopping.is_set():
                    terminal = {"status": "cancelled" if row[0] == "cancelling" else "interrupted", "error": "Preparation stopped before saving a new model setup. Try again when ready."}
                    return
                package.rename(self.root / "contexts" / name)
                job = self.get(owner, id).model_copy(update={"status": "completed", "stage": "ready", "context": name})
                db.execute("UPDATE context_preparations SET status=?,payload=? WHERE id=?", (job.status, job.model_dump_json(), id))
        except Exception:
            logging.getLogger(__name__).exception("Model preparation failed")
            terminal = {"status": "failed", "error": "Model preparation failed. Your saved investigations are unchanged. Try preparing a new sample."}
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            if terminal:
                (directory / "heartbeat").unlink(missing_ok=True)
                self.update(owner, id, **terminal)

    def close(self):
        with self.lock:
            self.stopping.set()
            thread = self.thread
        if thread:
            thread.join(10)
