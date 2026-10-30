"""Check that a worker returns exactly the local result for one synthetic job."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.experiments.provenance import source_digest  # noqa: E402
from app.faults.remote import JobManifest, canonical, contextFiles  # noqa: E402
from app.faults.replay import load_trusted_context  # noqa: E402
from app.faults.scenarios import FaultCase  # noqa: E402

CASE = {"components": [{"sensor": "vibration_rms", "kind": "stuck", "duration": "persistent", "onset_before_failure": 60},
    {"sensor": "oil_particles", "kind": "stuck", "duration": "persistent", "onset_before_failure": 60}]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="sidekick-worker")
    parser.add_argument("--command", help="Run the worker with this command instead of docker, e.g. 'python scripts/run_fault_job.py'.")
    args = parser.parse_args(argv)
    work = Path(tempfile.mkdtemp(prefix="sidekick-worker-"))
    (work / "outbox").mkdir()
    (work / "inbox").mkdir()
    work.chmod(0o777)
    (work / "inbox").chmod(0o777)
    subprocess.run([sys.executable, str(ROOT / "scripts/evaluate_fault_scenarios.py"), "--profile", "synthetic-rotating-v1",
        "--output", str(work / "context")], check=True, cwd=ROOT, capture_output=True)
    engine = load_trusted_context(work / "context", trusted=True)
    case = FaultCase.model_validate(CASE)
    manifest = JobManifest(jobId="c" * 32, contextFingerprint=engine.context_fingerprint, contextFiles=contextFiles(work / "context"),
        policyFingerprint=engine.policy.fingerprint, sourceDigest=source_digest(), scenario=case, maxSeconds=60, issuedAt=0)
    (work / "outbox" / "job.json").write_text(canonical(manifest.model_dump(mode="json")), encoding="utf-8")

    if args.command:
        command = [*shlex.split(args.command), "--manifest", str(work / "outbox/job.json"), "--context", str(work / "context"), "--inbox", str(work / "inbox")]
    else:
        command = ["docker", "run", "--rm", "--network", "none", "-v", f"{work}:/jobs", args.image,
            "--manifest", "/jobs/outbox/job.json", "--context", "/jobs/context", "--inbox", "/jobs/inbox"]
    subprocess.run([*command, "--trust-local-artifact", "--cpu-seconds", "300", "--memory-mb", "2048"], check=True, cwd=ROOT)

    results = list((work / "inbox").glob("*.json"))
    result = json.loads(results[0].read_text(encoding="utf-8")) if len(results) == 1 else {}
    expected = json.loads(canonical(engine.evaluate(case).model_dump(mode="json")))
    if result.get("status") != "completed" or result.get("evaluation") != expected:
        print(json.dumps({"status": result.get("status"), "error": result.get("error"), "results": len(results)}))
        return 1
    print(f"Worker result matches local evaluation for {case.scenario_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
