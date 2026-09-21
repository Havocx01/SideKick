"""Named, reproducible randomness.

Every random choice in the pipeline derives its seed from the base seed plus a
label describing what the choice is for. Two consequences matter for the
submission: a run can be repeated exactly, and fault placement for one sensor
cannot silently shift when an unrelated part of the matrix changes.
"""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np

_MAX_SEED = 2**31 - 1


def derive_seed(base: int, *parts: Any) -> int:
    """Derive a stable child seed from ``base`` and a label path.

    >>> derive_seed(7, "folds") == derive_seed(7, "folds")
    True
    >>> derive_seed(7, "folds") == derive_seed(7, "faults")
    False
    """
    digest = hashlib.blake2b(digest_size=8)
    digest.update(str(int(base)).encode("utf-8"))
    for part in parts:
        digest.update(b"\x1f")
        digest.update(str(part).encode("utf-8"))
    return int.from_bytes(digest.digest(), "big") % _MAX_SEED


def rng(base: int, *parts: Any) -> np.random.Generator:
    """A NumPy generator seeded from a labelled path."""
    return np.random.default_rng(derive_seed(base, *parts))
