"""Hash the source actually used, including uncommitted changes."""

import hashlib
from pathlib import Path


def source_digest() -> str:
    # Sorted by POSIX path with line endings normalized, so one source tree has one identity on every OS and checkout setting.
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256(b"sidekick-source-v2")
    for name, path in sorted((path.relative_to(root).as_posix(), path) for path in root.rglob("*.py")):
        digest.update(name.encode() + b"\0" + path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()
