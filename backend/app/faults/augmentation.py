"""Training-only support bounds for sampled augmentation faults."""

from app.config import ExperimentConfig


def augmentation_onset_bounds(config: ExperimentConfig, support: int) -> tuple[int, int]:
    lower = config.min_useful_lead + 5
    upper = min(max(120, config.horizon_cycles + 1, lower + 1), support + 1)
    if upper <= lower:
        raise ValueError(
            "Training augmentation needs longer histories: no supported fault onset "
            f"at or beyond {lower} cycles before failure (available: {support}). "
            "Supply longer complete histories or use a shorter warning window."
        )
    return lower, upper
