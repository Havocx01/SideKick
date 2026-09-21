"""Download and unpack the NASA C-MAPSS turbofan degradation archive.

Resolution order, so a portal outage cannot block the build:

1. ``--url`` if given.
2. The NASA open-data CKAN API, which holds the canonical resource URL.
3. A short list of known mirrors.
4. ``--archive`` pointing at an already-downloaded zip.

Usage
-----
    python scripts/fetch_data.py
    python scripts/fetch_data.py --archive ~/Downloads/CMAPSSData.zip
    python scripts/fetch_data.py --url https://example.org/CMAPSSData.zip
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

CKAN_ENDPOINT = (
    "https://data.nasa.gov/api/3/action/package_show?id=cmapss-jet-engine-simulated-data"
)
MIRRORS = (
    "https://ti.arc.nasa.gov/c/6/",
    "https://phm-datasets.s3.amazonaws.com/NASA/6.+Turbofan+Engine+Degradation+Simulation+Data+Set.zip",
)
USER_AGENT = "sidekick-abb-accelerator/0.1 (dataset fetch)"
EXPECTED = tuple(f"train_FD00{i}.txt" for i in range(1, 5))


def _request(url: str, timeout: float = 60.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def resolve_from_ckan() -> list[str]:
    """Ask the NASA portal for the archive's download URL."""
    try:
        payload = json.loads(_request(CKAN_ENDPOINT, timeout=30).decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        print(f"  portal lookup failed: {exc}")
        return []
    resources = payload.get("result", {}).get("resources", []) or []
    urls = [
        r.get("url")
        for r in resources
        if r.get("url") and str(r.get("url")).lower().endswith(".zip")
    ]
    return [u for u in urls if u]


def download(urls: list[str], destination: Path) -> Path | None:
    for url in urls:
        print(f"  trying {url}")
        try:
            data = _request(url, timeout=300)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"    failed: {exc}")
            continue
        if len(data) < 100_000:
            print(f"    rejected: only {len(data)} bytes, not an archive")
            continue
        destination.write_bytes(data)
        print(f"    downloaded {len(data) / 1e6:.1f} MB")
        return destination
    return None


def extract(archive: Path, target: Path) -> list[Path]:
    """Pull the data files out of the archive, ignoring directory nesting."""
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with zipfile.ZipFile(archive) as bundle:
        members = [m for m in bundle.namelist() if m.lower().endswith(".txt")]
        if not members:
            raise SystemExit(f"{archive} contains no .txt data files")
        for member in members:
            name = Path(member).name
            if not name:
                continue
            with bundle.open(member) as source, open(target / name, "wb") as sink:
                shutil.copyfileobj(source, sink)
            written.append(target / name)
    return written


def verify(target: Path) -> bool:
    missing = [name for name in EXPECTED if not (target / name).exists()]
    if missing:
        print(f"  missing expected files: {missing}")
        return False
    train = target / "train_FD001.txt"
    with open(train, encoding="utf-8", errors="ignore") as handle:
        lines = sum(1 for _ in handle)
    print(f"  train_FD001.txt has {lines} rows")
    # The published FD001 training file has 20631 rows across 100 engines.
    if lines < 20_000:
        print("  warning: fewer rows than the published FD001 training file")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="direct URL to CMAPSSData.zip")
    parser.add_argument("--archive", type=Path, help="path to an already-downloaded zip")
    parser.add_argument(
        "--target",
        type=Path,
        default=REPO_ROOT / "data" / "cmapss",
        help="directory to extract into (default: data/cmapss)",
    )
    parser.add_argument("--force", action="store_true", help="re-download even if present")
    args = parser.parse_args()

    target: Path = args.target
    if not args.force and (target / "train_FD001.txt").exists():
        print(f"C-MAPSS already present in {target}")
        verify(target)
        return 0

    archive: Path | None = args.archive
    temp_dir: Path | None = None

    if archive is None:
        candidates: list[str] = []
        if args.url:
            candidates.append(args.url)
        else:
            print("Resolving the download URL from the NASA open-data portal ...")
            candidates.extend(resolve_from_ckan())
            candidates.extend(MIRRORS)
        if not candidates:
            print("No candidate URLs available.")
            return _manual_instructions()

        temp_dir = Path(tempfile.mkdtemp(prefix="cmapss-"))
        archive = download(candidates, temp_dir / "CMAPSSData.zip")
        if archive is None:
            return _manual_instructions()
    elif not archive.exists():
        print(f"{archive} not found")
        return 1

    print(f"Extracting into {target} ...")
    written = extract(archive, target)
    print(f"  wrote {len(written)} files")

    if temp_dir is not None:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return 0 if verify(target) else 1


def _manual_instructions() -> int:
    print(
        "\nAutomatic download did not succeed. The dataset is small and can be\n"
        "fetched by hand:\n"
        "  1. Open https://data.nasa.gov/dataset/cmapss-jet-engine-simulated-data\n"
        "  2. Download CMAPSSData.zip\n"
        "  3. Re-run: python scripts/fetch_data.py --archive <path to zip>\n\n"
        "To keep working without it, every script accepts --synthetic, which uses\n"
        "the deterministic generator in app/data/synthetic.py. Results from it are\n"
        "labelled synthetic and are never reported as benchmark numbers.\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
