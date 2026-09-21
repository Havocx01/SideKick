"""Splits, candidates, cross-validated training, thresholds, calibration."""

from app.models.base import Candidate, DesignMatrix
from app.models.calibration import brier_score, calibration_report, reliability_bins
from app.models.candidates import (
    AgeBaselineCandidate,
    AugmentedXGBoostCandidate,
    LogisticRegressionCandidate,
    XGBoostCandidate,
    candidate_grid,
    rebuild_candidate,
)
from app.models.design import build_design, design_from_blocks, engine_blocks
from app.models.explain import explain_alert, global_importance
from app.models.splits import fold_pairs, make_splits, validate_splits
from app.models.thresholds import candidate_thresholds, choose_threshold
from app.models.train import TrainingResult, fit_final, train_development

__all__ = [
    "AgeBaselineCandidate",
    "AugmentedXGBoostCandidate",
    "Candidate",
    "DesignMatrix",
    "LogisticRegressionCandidate",
    "TrainingResult",
    "XGBoostCandidate",
    "brier_score",
    "build_design",
    "calibration_report",
    "candidate_grid",
    "candidate_thresholds",
    "choose_threshold",
    "design_from_blocks",
    "engine_blocks",
    "explain_alert",
    "fit_final",
    "fold_pairs",
    "global_importance",
    "make_splits",
    "rebuild_candidate",
    "reliability_bins",
    "train_development",
    "validate_splits",
]
