"""Write this coordinator's exact scoring dependency versions so a worker image can match them."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.experiments.validation import dependency_versions  # noqa: E402


def constraints() -> str:
    lines = []
    for name, version in sorted(dependency_versions().items()):
        lines.append(f"{name}=={version}")
        # Linux workers install the CPU-only wheel under a different name.
        if name == "xgboost":
            lines.append(f"xgboost-cpu=={version}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docker" / "worker-constraints.txt")
    args = parser.parse_args(argv)
    args.output.write_text(constraints(), encoding="utf-8")
    python = f"{sys.version_info.major}.{sys.version_info.minor}"
    print(f"Wrote {args.output}. Build a matching worker with:")
    print(f"docker build -f docker/worker.Dockerfile --build-arg PYTHON={python} -t sidekick-worker .")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
