"""Finite remote evaluation jobs exchanged through an outbox and inbox."""
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4

from pydantic import Field

from app.experiments.provenance import source_digest
from app.faults.evaluator import EvaluationStopped, FaultEvaluation
from app.faults.replay import MAX_JSON_BYTES
from app.faults.scenarios import FaultCase
from app.investigator.records import Frozen

MAX_ATTEMPTS = 3


class RemoteJobError(RuntimeError):
    pass


class JobManifest(Frozen):
    version: int = Field(default=1, ge=1, le=1)
    jobId: str = Field(pattern=r"^[a-f0-9]{32}$")
    contextFingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    contextFiles: dict[str, str]
    policyFingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    sourceDigest: str
    scenario: FaultCase
    maxSeconds: float = Field(gt=0, le=3600)
    issuedAt: float


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def contextFiles(directory: Path) -> dict[str, str]:
    return json.loads((Path(directory) / "manifest.json").read_text(encoding="utf-8"))["files"]


def writeAtomic(path: Path, text: str):
    pending = path.with_suffix(path.suffix + ".pending")
    pending.write_text(text, encoding="utf-8")
    pending.replace(path)


def runJob(manifestPath: Path, context: Path, inbox: Path, *, trusted=False):
    """Evaluate one manifest and write one result artifact. Used inside the worker container."""
    from app.faults.replay import load_trusted_context
    text = Path(manifestPath).read_text(encoding="utf-8")
    manifest = JobManifest.model_validate_json(text)
    output = Path(inbox) / f"{manifest.jobId}.{uuid4().hex[:8]}.json"
    result = {"jobId": manifest.jobId, "manifestDigest": sha(canonical(json.loads(text)))}
    try:
        if contextFiles(context) != manifest.contextFiles or source_digest() != manifest.sourceDigest:
            raise RemoteJobError("Worker context or source does not match the manifest")
        evaluator = load_trusted_context(context, trusted=trusted)
        if evaluator.context_fingerprint != manifest.contextFingerprint or evaluator.policy.fingerprint != manifest.policyFingerprint:
            raise RemoteJobError("Worker context identity does not match the manifest")
        deadline = time.monotonic() + manifest.maxSeconds
        evaluation = evaluator.evaluate(manifest.scenario, cancelled=lambda: time.monotonic() >= deadline)
        document = canonical(evaluation.model_dump(mode="json"))
        result.update(status="completed", evaluation=json.loads(document), evaluationDigest=sha(document))
    except (ValueError, RemoteJobError, EvaluationStopped) as error:
        result.update(status="failed", error=f"{type(error).__name__}: {error}"[:300])
    writeAtomic(output, canonical(result))
    return output


class RemoteExecutor:
    """Runner executor that dispatches each case as a job and accepts exactly one matching result."""

    def __init__(self, evaluator, context: Path, outbox: Path, inbox: Path, *, transferConsent=False, poll=.2, maxAttempts=MAX_ATTEMPTS,
            clock=time.monotonic, sleep=time.sleep):
        # Context packages contain raw development data, so sending them anywhere needs explicit consent.
        if not transferConsent:
            raise PermissionError("Remote execution sends the private context package; explicit transfer consent is required")
        self.evaluator, self.context = evaluator, Path(context)
        self.outbox, self.inbox = Path(outbox), Path(inbox)
        self.outbox.mkdir(parents=True, exist_ok=True)
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.poll, self.maxAttempts, self.clock, self.sleep = poll, maxAttempts, clock, sleep
        self.files = contextFiles(self.context)
        self.jobs = []

    def __call__(self, case, cancelled=None):
        failures = []
        for _ in range(self.maxAttempts):
            manifest = JobManifest(jobId=uuid4().hex, contextFingerprint=self.evaluator.context_fingerprint, contextFiles=self.files,
                policyFingerprint=self.evaluator.policy.fingerprint, sourceDigest=source_digest(), scenario=case,
                maxSeconds=float(self.evaluator.policy.max_seconds), issuedAt=time.time())
            text = canonical(manifest.model_dump(mode="json"))
            writeAtomic(self.outbox / f"{manifest.jobId}.json", text)
            self.jobs.append(manifest.jobId)
            result = self.wait(manifest, sha(text), cancelled)
            if result["status"] == "completed":
                return self.accept(manifest, result)
            failures.append(result["error"])
        raise RemoteJobError(f"Remote job failed {len(failures)} times: {failures[-1]}")

    def wait(self, manifest, digest, cancelled):
        deadline = self.clock() + manifest.maxSeconds + 60
        while True:
            for path in sorted(self.inbox.glob(f"{manifest.jobId}.*.json")):
                if path.stat().st_size > MAX_JSON_BYTES:
                    continue
                try:
                    result = json.loads(path.read_text(encoding="utf-8"))
                except ValueError:
                    continue
                # Duplicate deliveries are expected; only a result for this exact manifest is considered.
                if result.get("jobId") == manifest.jobId and result.get("manifestDigest") == digest and result.get("status") in {"completed", "failed"}:
                    return result
            if cancelled is not None and cancelled():
                raise EvaluationStopped("Remote job cancelled")
            if self.clock() >= deadline:
                return {"status": "failed", "error": "Remote job timed out"}
            self.sleep(self.poll)

    def accept(self, manifest, result):
        document = canonical(result.get("evaluation"))
        if sha(document) != result.get("evaluationDigest"):
            raise RemoteJobError("Remote result does not match its checksum")
        evaluation = FaultEvaluation.model_validate_json(document)
        if (evaluation.scenario_id != manifest.scenario.scenario_id or evaluation.context_fingerprint != manifest.contextFingerprint
                or evaluation.policy_fingerprint != manifest.policyFingerprint):
            raise RemoteJobError("Remote result belongs to a different case or context")
        return evaluation
