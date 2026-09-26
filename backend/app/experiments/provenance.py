"""Hash the source actually used, including uncommitted changes."""

import hashlib
from pathlib import Path


def source_digest() -> str:
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256(b"sidekick-source-v1")
    for path in sorted(root.rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()
