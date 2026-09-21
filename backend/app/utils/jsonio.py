"""Canonical JSON serialisation, hashing and atomic writes.

Hashes are used for two claims in the submission: that a reported metric was
computed from a specific dataset, and that repeating a run reproduces it. Both
require a byte-stable encoding, so every hash and file write goes through here.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any


def _default(obj: Any) -> Any:
    """Encode NumPy scalars, arrays, sets, paths and pydantic models."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "item") and hasattr(obj, "dtype") and not hasattr(obj, "__len__"):
        return obj.item()
    if hasattr(obj, "tolist"):
        return obj.tolist()
    if isinstance(obj, (set, frozenset, tuple)):
        return list(obj)
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"cannot serialise {type(obj)!r}")


def sanitise(obj: Any) -> Any:
    """Replace non-finite floats with ``None`` so the result is valid JSON."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: sanitise(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitise(v) for v in obj]
    return obj


def canonical_dumps(obj: Any) -> str:
    """Byte-stable JSON: sorted keys, no incidental whitespace."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), default=_default, allow_nan=False
    )


def hash_obj(obj: Any, length: int = 16) -> str:
    """SHA-256 of the canonical encoding of ``obj``."""
    return hashlib.sha256(canonical_dumps(sanitise(obj)).encode("utf-8")).hexdigest()[:length]


def hash_file(path: Path, length: int = 16) -> str:
    """SHA-256 of a file's contents, read in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()[:length]


def write_json(path: Path, obj: Any, *, indent: int | None = 2) -> Path:
    """Write JSON atomically, so a crash cannot leave a truncated record."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(sanitise(obj), indent=indent, default=_default, allow_nan=False)
    # delete=False is required: the file has to outlive the handle so os.replace can
    # move it into place, which is what makes the write atomic.
    handle = tempfile.NamedTemporaryFile(  # noqa: SIM115
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    )
    try:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    finally:
        handle.close()
    os.replace(handle.name, path)
    return path


def read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)
