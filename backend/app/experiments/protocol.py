"""Resolve and check the immutable protocol before a worker is admitted."""

from dataclasses import replace

from app.config import EXPERIMENT
from app.faults.matrix import required_scenarios
from app.schemas import ExperimentProtocol, FaultScenario


def resolve_protocol(request, dataset):
    if request.protocol is not None and not request.protocol.scenarios:
        raise ValueError("Add at least one required sensor fault to the protocol.")
    protocol = request.protocol or ExperimentProtocol(
        min_detection_fraction=request.min_detection_fraction,
        max_early_alarm_burden=request.max_early_alarm_burden,
    )
    if not protocol.scenarios:
        sensors = [s["name"] for s in dataset["profile"]["sensors"] if s["varies"]]
        defaults = required_scenarios(sensors, EXPERIMENT)
        protocol = protocol.model_copy(update={"scenarios": [FaultScenario(fault=s) for s in defaults]})
    return ExperimentProtocol.model_validate(protocol.model_dump())


def protocol_config(protocol, *, hosted=False):
    config = replace(
        EXPERIMENT,
        protocol_revision=4,
        min_useful_lead=protocol.min_useful_lead,
        late_window_end=protocol.min_useful_lead - 1,
        horizon_cycles=protocol.horizon_cycles,
        transition_band_end=protocol.transition_band_end,
        min_detection_fraction=protocol.min_detection_fraction,
        max_early_alarm_burden=protocol.max_early_alarm_burden,
        base_seed=protocol.base_seed,
        configs_per_candidate=1 if hosted else EXPERIMENT.configs_per_candidate,
        fault_scenarios=tuple(s.model_dump(mode="json") for s in protocol.scenarios),
    )
    config.validate()
    return config


def check_coverage(dataset, protocol):
    """Coverage uses development histories only; reserved histories remain unexamined."""
    from app.models.splits import make_splits

    splits = make_splits(dataset, dataset.config)
    development = dataset.subset(splits.development)
    sensors = set(dataset.sensors)
    for entry in protocol.scenarios:
        spec = entry.fault
        if spec.sensor not in sensors:
            raise ValueError(f"Sensor {spec.sensor!r} is not in the confirmed mapping.")
        if entry.required:
            for equipment in splits.development:
                frame = development.frame[development.frame["equipment_id"] == equipment]
                if int(frame["rul"].max()) < spec.onset_before_failure:
                    raise ValueError(f"Required case {spec.label()} starts before history {equipment}. Use a later onset or supply a longer history.")
    return splits
