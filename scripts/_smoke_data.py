"""Temporary smoke check for the data layer against real C-MAPSS FD001."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.data import load_cmapss, profile_dataset  # noqa: E402

dataset = load_cmapss("FD001")
print(dataset.describe())
print("source:", dataset.source)
print("hash:", dataset.data_hash)
print("rows:", len(dataset.frame), "(expected 20631)")
print("engines:", len(dataset.equipment_ids), "(expected 100)")
lifetimes = list(dataset.lifetimes.values())
print("lifetime min/median/max:", min(lifetimes), sorted(lifetimes)[len(lifetimes) // 2], max(lifetimes))
print("scorable cycles:", int(dataset.scorable_mask().sum()))
print("positive labels:", int(dataset.label_vector().sum()))
print(dataset.frame.head(3).to_string())

profile = profile_dataset(dataset)
print("\nusable:", profile.usable)
for finding in profile.findings:
    print(f"  [{finding.severity.value:8}] {finding.code}: {finding.message}")

constant = [s.name for s in profile.sensors if s.constant]
varying = [s.name for s in profile.sensors if s.varies]
print("\nconstant channels:", constant)
print("varying channels:", len(varying), varying)
