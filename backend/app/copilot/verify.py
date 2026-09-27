"""Numeric claim verification."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from typing import Any

from app.schemas import NumericClaim

#: Matches integers, decimals and percentages, with optional thousands separators.
_NUMBER = re.compile(r"(?<![\w.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?!\w|\.\d)(?:\s*%)?")


def collect_values(payload: Any, *, depth: int = 0) -> set[float]:
    values: set[float] = set()
    if depth > 8:
        return values

    if isinstance(payload, bool):
        return values
    if isinstance(payload, (int, float)):
        number = float(payload)
        if math.isfinite(number):
            values.add(number)
        return values
    if isinstance(payload, str):
        for match in _NUMBER.finditer(payload):
            try:
                raw = match.group(0).strip()
                value = float(raw.replace(",", "").rstrip("% ").strip())
                values.add(value / 100 if raw.endswith("%") else value)
            except ValueError:
                continue
        return values
    if isinstance(payload, dict):
        for key, value in payload.items():
            values |= collect_values(value, depth=depth + 1)
            if isinstance(key, str):
                values |= collect_values(key, depth=depth + 1)
        return values
    if isinstance(payload, Iterable):
        items = list(payload)
        # A list's own length is a legitimate claim: "sixteen sensors were tested".
        values.add(float(len(items)))
        for item in items:
            values |= collect_values(item, depth=depth + 1)
        return values
    return values


def extract_claims(text: str) -> list[tuple[str, float]]:
    claims: list[tuple[str, float]] = []
    for match in _NUMBER.finditer(text):
        raw = match.group(0).strip()
        digits = raw.rstrip("% ").replace(",", "").strip()
        try:
            value = float(digits)
        except ValueError:
            continue
        claims.append((raw, value))
    return claims


def matches(value: float, allowed: set[float], tolerance: float = 1e-9) -> float | None:
    best: float | None = None
    bestGap = float("inf")
    for candidate in allowed:
        gap = abs(value - candidate)
        if gap <= tolerance and gap < bestGap:
            best, bestGap = candidate, gap
    return best


def verify_answer(text: str, tool_results: list[Any]) -> list[NumericClaim]:
    allowed: set[float] = set()
    for result in tool_results:
        allowed |= collect_values(result)

    claims: list[NumericClaim] = []
    for raw, value in extract_claims(text):
        digits = raw.rstrip("% ").replace(",", "")
        places = len(digits.split(".")[1]) if "." in digits else 0
        scale = 100 if raw.endswith("%") else 1
        # Permit only rounding at the precision actually printed, not a blanket
        # relative tolerance. An integer count must match exactly.
        tolerance = (0.5 * 10**-places / scale + 1e-12) if places or scale == 100 else 1e-9
        matched = matches(value / scale, allowed, tolerance)
        claims.append(
            NumericClaim(
                text=raw,
                value=value,
                verified=matched is not None,
                matched_metric=(f"{matched:g}" if matched is not None else None),
            )
        )
    return claims


def unverified(claims: list[NumericClaim]) -> list[NumericClaim]:
    return [claim for claim in claims if not claim.verified]


def annotate(text: str, claims: list[NumericClaim]) -> str:
    outstanding = unverified(claims)
    if not outstanding:
        return text
    figures = ", ".join(sorted({claim.text for claim in outstanding}))
    return (
        f"{text}\n\n**Unverified figures:** {figures}. These could not be matched to a "
        "recorded metric and should not be relied on."
    )
