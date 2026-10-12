"""Capture small diagnostic facts while the evaluated objects still exist."""
from collections import defaultdict

from app.features.build import FEATURE_KINDS, FeatureBuilder, Preprocessor
from app.schemas import FoldFaultSummary, RecordedPreprocessing


def recorded_diagnostics(result):
    training = result.training
    folds = training.folds
    preprocessing = None
    if folds and all(type(fold.builder) is FeatureBuilder and type(fold.preprocessor) is Preprocessor for fold in folds):
        windows = {fold.builder.window for fold in folds}
        if len(windows) == 1:
            scaling = {}
            for key in training.specs:
                methods = set()
                for fold in folds:
                    candidate = fold.candidates[key]
                    pipeline = getattr(candidate, "_pipeline", None)
                    scaler = pipeline.named_steps.get("scale") if pipeline is not None else None
                    methods.add("standard_scaler" if type(scaler).__name__ == "StandardScaler" else
                        "not_applicable" if not candidate.uses_sensors else
                        "none" if getattr(candidate, "booster", None) is not None else "unavailable")
                scaling[key] = next(iter(methods)) if len(methods) == 1 else "varies_across_folds"
            preprocessing = RecordedPreprocessing(feature_window=next(iter(windows)), feature_kinds=list(FEATURE_KINDS),
                imputation="training_median_before_windowing", missingness="trailing_missing_fraction",
                all_missing_fill="zero_with_missingness_retained", fitting_scope="training_equipment_only_in_each_development_fold",
                scaling=scaling)
    membership = {equipment: index + 1 for index, fold in enumerate(training.splits.folds) for equipment in fold}
    summaries = []
    for (candidate, scenario), scorings in sorted(result.matrix.equipment_metrics.items()):
        grouped = defaultdict(list)
        for scoring in scorings:
            if scoring.outcome.equipment_id in membership:
                grouped[membership[scoring.outcome.equipment_id]].append(scoring.outcome)
        for fold, outcomes in sorted(grouped.items()):
            summaries.append(FoldFaultSummary(candidate=candidate, scenario_id=scenario, fold=fold,
                equipment_count=len(outcomes), detected=sum(item.detected for item in outcomes),
                late=sum(item.late for item in outcomes), missed=sum(item.missed for item in outcomes)))
    return preprocessing, summaries
