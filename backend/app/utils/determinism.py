"""Named, reproducible randomness."""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np

_MAX_SEED = 2**31 - 1


def derive_seed(base: int, *parts: Any) -> int:
    digest = hashlib.blake2b(digest_size=8)
    digest.update(str(int(base)).encode("utf-8"))
    for part in parts:
        digest.update(b"\x1f")
        digest.update(str(part).encode("utf-8"))
    return int.from_bytes(digest.digest(), "big") % _MAX_SEED


def rng(base: int, *parts: Any) -> np.random.Generator:
    return np.random.default_rng(derive_seed(base, *parts))
