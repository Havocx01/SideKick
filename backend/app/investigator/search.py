"""Scenario suites and search strategies compared under one budget."""
import json

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


SEVERITIES = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0)


def kindsFor(policy, sensor):
    if policy.profile is not None:
        return [kind.value for kind in next(rule for rule in policy.profile.sensors if rule.sensor == sensor).kinds]
    return ["dropout", "stuck", "drift"]


def onsets(policy, config):
    return list(range(-(-config.min_useful_lead // 10) * 10, min(policy.max_onset, 120) + 1, 10))


def atom(policy, config, sensor, kind, onset, rng):
    data = {"sensor": sensor, "kind": kind, "duration": "persistent", "onset_before_failure": onset}
    if kind == "drift":
        cap = policy.max_severity_sd
        if policy.profile is not None:
            rule = next(rule for rule in policy.profile.sensors if rule.sensor == sensor)
            cap = min(cap, rule.max_severity_sd or cap)
        data.update(severity_sd=float(rng.choice([value for value in SEVERITIES if value <= cap])), sign=int(rng.choice([-1, 1])), ramp_cycles=10)
    return data


def randomCase(policy, config, rng):
    groups = policy.allowed_groups or (tuple(policy.allowed_sensors),)
    group = list(groups[int(rng.integers(len(groups)))])
    size = int(rng.integers(1, min(policy.max_components, len(group)) + 1))
    sensors = sorted(rng.choice(group, size=size, replace=False).tolist())
    return {"components": [atom(policy, config, sensor, str(rng.choice(kindsFor(policy, sensor))), int(rng.choice(onsets(policy, config))), rng)
        for sensor in sensors]}


def fixedSuite(policy, config):
    # The engineer's usual checklist: every permitted single-channel fault at the warning horizon.
    onset = min(max(config.horizon_cycles, config.min_useful_lead), policy.max_onset)
    cases = []
    for sensor in policy.allowed_sensors:
        for kind in kindsFor(policy, sensor):
            data = {"sensor": sensor, "kind": kind, "duration": "persistent", "onset_before_failure": onset}
            if kind == "drift":
                data.update(severity_sd=1.0, sign=1, ramp_cycles=10)
            cases.append({"components": [data]})
    return cases


def neighbor(case, policy, config, rng):
    # Discrete encoding: change one onset, one severity, one kind, or add/drop one channel in the same group.
    data = json.loads(json.dumps(case))
    parts = data["components"]
    target = parts[int(rng.integers(len(parts)))]
    move = str(rng.choice(["onset", "severity", "kind", "size"]))
    if move == "onset":
        target["onset_before_failure"] = int(rng.choice(onsets(policy, config)))
    elif move == "severity" and target["kind"] == "drift":
        target["severity_sd"] = float(rng.choice(SEVERITIES))
    elif move == "kind":
        replacement = atom(policy, config, target["sensor"], str(rng.choice(kindsFor(policy, target["sensor"]))), target["onset_before_failure"], rng)
        parts[parts.index(target)] = replacement
    elif len(parts) > 1 and rng.random() < .5:
        parts.remove(target)
    else:
        sensors = {item["sensor"] for item in parts}
        group = next((group for group in policy.allowed_groups if sensors <= set(group)), policy.allowed_sensors)
        extra = [sensor for sensor in group if sensor not in sensors]
        if extra and len(parts) < policy.max_components:
            sensor = str(rng.choice(extra))
            parts.append(atom(policy, config, sensor, str(rng.choice(kindsFor(policy, sensor))), target["onset_before_failure"], rng))
    return data
