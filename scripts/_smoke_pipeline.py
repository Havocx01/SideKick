"""Temporary end-to-end smoke check on a small synthetic dataset."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import EXPERIMENT  # noqa: E402
from app.data import make_synthetic_dataset  # noqa: E402
from app.scoring.pipeline import evaluate  # noqa: E402

config = replace(EXPERIMENT, holdout_engines=6, n_folds=3, configs_per_candidate=1)
config.validate()

dataset = make_synthetic_dataset(n_equipment=30, min_life=130, max_life=220, config=config)
print(dataset.describe())

result = evaluate(
    dataset,
    config=config,
    include_full_matrix=False,
    fault_sensors=["temp_bearing", "vibration_rms", "pressure_out"],
    augmentation_copies=1,
)

print("\nrequired scenarios:", len(result.required_scenario_ids))
print("scenario results:", len(result.scenario_results))
print("outcome:", result.selection.outcome.value)
print("\n{:<34} {:>6} {:>8} {:>8} {:>8} {:>7}".format("candidate", "thresh", "clean", "mean-req", "worst", "burden"))
for verdict in result.selection.ranked:
    print(
        "{:<34} {:>6.3f} {:>8.0%} {:>8.0%} {:>8.0%} {:>7.1%}".format(
            f"{verdict.candidate.value}/{verdict.config_id}",
            verdict.threshold,
            verdict.clean.detection_fraction,
            verdict.mean_detection_required,
            verdict.worst_detection_required,
            verdict.clean.early_alarm_burden,
        )
    )

if result.selection.recommended:
    rec = result.selection.recommended
    print(f"\nrecommended: {rec.candidate.value}/{rec.config_id}")
    print(f"  clean detection {rec.clean.detection_fraction:.0%} "
          f"[{rec.clean.detection_ci.lower:.2f}, {rec.clean.detection_ci.upper:.2f}]")
    print(f"  median lead time {rec.clean.median_lead_time} cycles")
    print(f"  late {rec.clean.late}, missed {rec.clean.missed} of {rec.clean.engines}")
else:
    print("\nno candidate qualified")

for note in result.selection.notes:
    print("note:", note)
for item in result.selection.uncertain_comparisons:
    print("uncertain:", item)

print("\ncalibration:")
for report in result.calibration:
    print(f"  {report.candidate.value}/{report.config_id}: Brier {report.brier:.4f}, {len(report.bins)} bins")

print("\nage baseline invariance check:")
age = [n for n in result.training.specs if n.startswith("age_baseline")][0]
per_scenario = result.matrix.for_candidate(age)
detections = {sid: m.detection_fraction for sid, m in per_scenario.items()}
print("  distinct detection values under fault:", sorted(set(round(v, 6) for v in detections.values())))
print("  clean detection:", round(result.clean[age].detection_fraction, 6))
