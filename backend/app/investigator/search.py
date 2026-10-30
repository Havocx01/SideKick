"""Deterministic scenario suites shared by search strategies."""
from app.faults.scenarios import FaultCase


def seedSuite(policy, config, count=3) -> list[dict]:
    # One channel per declared group first, so the first measurements span the profile.
    groups = policy.allowed_groups or tuple((sensor,) for sensor in policy.allowed_sensors)
    order = []
    for group in groups:
        first = next((sensor for sensor in group if sensor not in order), None)
        if first is not None:
            order.append(first)
    order += [sensor for sensor in policy.allowed_sensors if sensor not in order]

    rules = {rule.sensor: rule for rule in policy.profile.sensors} if policy.profile is not None else {}
    onset = min(max(config.horizon_cycles, config.min_useful_lead), policy.max_onset)
    proposals = []
    for sensor in order:
        kinds = [kind.value for kind in rules[sensor].kinds] if sensor in rules else ["stuck", "dropout"]
        kind = "stuck" if "stuck" in kinds else "dropout" if "dropout" in kinds else None
        if kind is None:
            continue
        case = FaultCase(components=[{"sensor": sensor, "kind": kind, "duration": "persistent", "onset_before_failure": onset}])
        try:
            policy.check(case, config)
        except ValueError:
            continue
        proposals.append({"scenario": case.model_dump(mode="json"), "reason": f"Seed suite: {kind} {sensor} {onset} cycles before failure."})
        if len(proposals) == count:
            break
    return proposals
