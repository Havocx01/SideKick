"""Numeric claim verification.

The copilot is allowed to write prose. It is not allowed to invent figures. Every
number in a drafted answer is checked against the values the tools actually
returned, and anything unmatched is reported rather than displayed as fact.

This is a guard, not a proof of correctness: it catches a fabricated or misremembered
figure, and it does not check that a correctly quoted number is being used to
support a sensible argument. The interface says as much, because overstating what
the check does would be the same failure it exists to prevent.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from app.schemas import NumericClaim

#: Matches integers, decimals and percentages, with optional thousands separators.
_NUMBER = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?\s*(%)?")

#: Numbers that carry no claim: small counts in ordinary prose, and the
#: percentage bounds themselves.
_FREE = {0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 100.0}

RELATIVE_TOLERANCE = 0.011
ABSOLUTE_TOLERANCE = 0.006


def collect_values(payload: Any, *, depth: int = 0) -> set[float]:
    """Every number reachable in a tool result, plus its percentage form.

    A tool returning ``0.93`` licenses an answer saying either "0.93" or "93%",
    so both forms are admitted.
    """
    values: set[float] = set()
    if depth > 8:
        return values

    if isinstance(payload, bool):
        return values
    if isinstance(payload, (int, float)):
        number = float(payload)
        values.add(number)
        values.add(number * 100.0)
        # Rounded forms, since an answer will say "93%" rather than "93.33%".
        for digits in (0, 1, 2):
            values.add(round(number, digits))
            values.add(round(number * 100.0, digits))
        return values
    if isinstance(payload, str):
        for match in _NUMBER.finditer(payload):
            try:
                values.add(float(match.group(0).replace(",", "").rstrip("% ").strip()))
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
    """Pull numeric claims out of drafted prose."""
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


def matches(value: float, allowed: set[float]) -> float | None:
    """The closest admissible value, or ``None`` if nothing is close enough."""
    best: float | None = None
    best_gap = float("inf")
    for candidate in allowed:
        gap = abs(value - candidate)
        tolerance = max(ABSOLUTE_TOLERANCE, RELATIVE_TOLERANCE * abs(candidate))
        if gap <= tolerance and gap < best_gap:
            best, best_gap = candidate, gap
    return best


def verify_answer(text: str, tool_results: list[Any]) -> list[NumericClaim]:
    """Check every number in ``text`` against the values the tools returned."""
    allowed: set[float] = set(_FREE)
    for result in tool_results:
        allowed |= collect_values(result)

    claims: list[NumericClaim] = []
    for raw, value in extract_claims(text):
        if value in _FREE:
            claims.append(NumericClaim(text=raw, value=value, verified=True, matched_metric="prose"))
            continue
        matched = matches(value, allowed)
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


def correction_prompt(claims: list[NumericClaim]) -> str:
    """Message sent back to the model when a figure could not be matched."""
    figures = ", ".join(sorted({claim.text for claim in unverified(claims)}))
    return (
        "These figures in your answer do not match any value returned by the tools: "
        f"{figures}. Restate the answer using only numbers that appear in the tool "
        "results. If you need a number you do not have, call the relevant tool, or "
        "say plainly that it was not measured."
    )


def annotate(text: str, claims: list[NumericClaim]) -> str:
    """Append a visible warning when figures remain unmatched."""
    outstanding = unverified(claims)
    if not outstanding:
        return text
    figures = ", ".join(sorted({claim.text for claim in outstanding}))
    return (
        f"{text}\n\n**Unverified figures:** {figures}. These could not be matched to a "
        "recorded metric and should not be relied on."
    )
