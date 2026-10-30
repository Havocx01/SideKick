"""Versioned equipment fault profiles."""
import json
from pathlib import Path

from app.faults.scenarios import FaultPolicy, Profile

ROOT = Path(__file__).resolve().parent


def names() -> list[str]:
    return sorted(path.stem for path in ROOT.glob("*.json"))


def loadPolicy(name: str, **limits) -> FaultPolicy:
    if name not in names():
        raise ValueError(f"Unknown fault profile: {name}")
    data = json.loads((ROOT / f"{name}.json").read_text(encoding="utf-8"))
    bounds, groups = data.pop("bounds"), data.pop("groups")
    profile = Profile.model_validate(data)
    label = "Synthetic" if profile.synthetic else "Declared"
    return FaultPolicy(allowed_sensors=tuple(rule.sensor for rule in profile.sensors), allowed_groups=tuple(tuple(group) for group in groups),
        assumptions=f"{label} {profile.equipment} profile v{profile.version}; bounds are not equipment-validated.", profile=profile, **bounds, **limits)
