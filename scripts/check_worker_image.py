"""Check exact replay between a coordinator and worker using the same numerical runtime."""
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


def prepare(work):
    (work / "outbox").mkdir(exist_ok=True)
    (work / "inbox").mkdir(exist_ok=True)
    subprocess.run([sys.executable, str(ROOT / "scripts/evaluate_fault_scenarios.py"), "--profile", "synthetic-rotating-v1",
        "--output", str(work / "context")], check=True, cwd=ROOT, capture_output=True)
    engine = load_trusted_context(work / "context", trusted=True)
    case = FaultCase.model_validate(CASE)
    manifest = JobManifest(jobId="c" * 32, contextFingerprint=engine.context_fingerprint, contextFiles=contextFiles(work / "context"),
        policyFingerprint=engine.policy.fingerprint, sourceDigest=source_digest(), scenario=case, maxSeconds=60, issuedAt=0)
    (work / "outbox" / "job.json").write_text(canonical(manifest.model_dump(mode="json")), encoding="utf-8")
    (work / "expected.json").write_text(canonical(engine.evaluate(case).model_dump(mode="json")), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="sidekick-worker")
    parser.add_argument("--command", help="Run both preparation and this worker command locally instead of Docker.")
    parser.add_argument("--prepare", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.prepare:
        prepare(args.prepare)
        return 0
    work = Path(tempfile.mkdtemp(prefix="sidekick-worker-"))
    (work / "outbox").mkdir()
    (work / "inbox").mkdir()
    work.chmod(0o777)
    (work / "inbox").chmod(0o777)

    if args.command:
        prepare(work)
        command = [*shlex.split(args.command), "--manifest", str(work / "outbox/job.json"), "--context", str(work / "context"), "--inbox", str(work / "inbox")]
    else:
        # Matching package versions alone does not ensure identical Windows and Linux prediction bytes.
        subprocess.run(["docker", "run", "--rm", "--network", "none", "--entrypoint", "python", "-v", f"{work}:/jobs",
            "-v", f"{ROOT / 'scripts/check_worker_image.py'}:/app/scripts/check_worker_image.py:ro",
            args.image, "/app/scripts/check_worker_image.py", "--prepare", "/jobs"], check=True, cwd=ROOT)
        command = ["docker", "run", "--rm", "--network", "none", "-v", f"{work}:/jobs", args.image,
            "--manifest", "/jobs/outbox/job.json", "--context", "/jobs/context", "--inbox", "/jobs/inbox"]
    subprocess.run([*command, "--trust-local-artifact", "--cpu-seconds", "300", "--memory-mb", "2048"], check=True, cwd=ROOT)

    results = list((work / "inbox").glob("*.json"))
    result = json.loads(results[0].read_text(encoding="utf-8")) if len(results) == 1 else {}
    expected = json.loads((work / "expected.json").read_text(encoding="utf-8"))
    if result.get("status") != "completed" or result.get("evaluation") != expected:
        print(json.dumps({"status": result.get("status"), "error": result.get("error"), "results": len(results)}))
        return 1
    runtime = "local" if args.command else "container coordinator"
    print(f"Worker result matches {runtime} evaluation for {expected['scenario_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
