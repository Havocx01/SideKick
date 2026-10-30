"""Evaluate one remote fault job manifest under hard CPU and memory limits, then exit."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def limit(cpuSeconds, memoryMb):
    # A native scoring call cannot be interrupted cooperatively, so the kernel enforces these.
    try:
        import resource
    except ImportError:
        return False
    resource.setrlimit(resource.RLIMIT_CPU, (cpuSeconds, cpuSeconds + 5))
    resource.setrlimit(resource.RLIMIT_AS, (memoryMb * 1024 * 1024, memoryMb * 1024 * 1024))
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True, help="The context package named by the manifest.")
    parser.add_argument("--inbox", type=Path, required=True, help="Where the result artifact is written.")
    parser.add_argument("--trust-local-artifact", action="store_true", help="Only for a package you produced and trust; joblib can execute code.")
    parser.add_argument("--cpu-seconds", type=int, default=600)
    parser.add_argument("--memory-mb", type=int, default=4096)
    args = parser.parse_args(argv)
    limit(args.cpu_seconds, args.memory_mb)
    from app.faults.remote import runJob
    print(runJob(args.manifest, args.context, args.inbox, trusted=args.trust_local_artifact))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
