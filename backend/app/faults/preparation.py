from dataclasses import replace

from app.config import EXPERIMENT
from app.data.synthetic import make_synthetic_dataset
from app.faults.evaluator import FixedDevelopmentEvaluator
from app.faults.profiles import loadPolicy
from app.faults.replay import export_evaluation
from app.faults.scenarios import FaultCase, FaultPolicy
from app.models.candidates import AgeBaselineCandidate, LogisticRegressionCandidate
from app.models.train import train_development
from app.scoring.pipeline import pick_thresholds
from app.scoring.selection import default_criteria


def prepareSynthetic(directory, *, profile=None, case=None, progress=None):
    def stage(value):
        if progress:
            progress(value)

    stage("generating")
    config = replace(EXPERIMENT, holdout_engines=4, n_folds=2, feature_window=5,
        horizon_cycles=20, min_useful_lead=5, late_window_end=4, transition_band_end=30, configs_per_candidate=1)
    dataset = make_synthetic_dataset(n_equipment=26, min_life=85, max_life=100, config=config)
    policy = loadPolicy(profile) if profile else FaultPolicy(allowed_sensors=tuple(dataset.sensors))
    case = case or FaultCase(components=[
        {"sensor": "temp_bearing", "kind": "dropout", "duration": "persistent", "onset_before_failure": 40},
        {"sensor": "vibration_rms", "kind": "drift", "duration": "persistent", "onset_before_failure": 40,
            "severity_sd": 1.5, "sign": 1, "ramp_cycles": 10}])
    policy.check(case, config)
    stage("training")
    training = train_development(dataset, config=config,
        candidates=[LogisticRegressionCandidate("lr-probe", {"max_iter": 300}), AgeBaselineCandidate("age-probe")])
    stage("calibrating")
    choices = pick_thresholds(training, default_criteria(config), config=config)
    evaluator = FixedDevelopmentEvaluator(training, {name: choice.threshold for name, choice in choices.items()}, policy)
    stage("checking")
    result = evaluator.evaluate(case)
    export_evaluation(evaluator, result, directory)
    return result
