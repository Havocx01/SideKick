"""Fixed, grouped-development evaluation. No fitting or reserved scoring is exposed."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import math
import time
from typing import Literal

import joblib
import numpy as np
from pydantic import Field

from app.experiments.provenance import source_digest
from app.faults.scenarios import ComponentApplication, FaultCase, FaultPolicy, apply_case, fingerprint
from app.features.build import FeatureBuilder
from app.models.design import EngineBlock, design_from_blocks, engine_blocks
from app.models.splits import validate_splits
from app.schemas import AlertMetrics, EngineOutcome, Strict
from app.scoring.metrics import aggregate, score_engine


class EvaluationStopped(RuntimeError):
    pass


class Exclusion(Strict):
    equipment_id: str
    reasons: list[str]


class HistoryApplication(Strict):
    equipment_id: str
    components: list[ComponentApplication]


class MatchedOutcome(Strict):
    equipment_id: str
    clean: EngineOutcome
    faulted: EngineOutcome
    clean_prediction_digest: str
    faulted_prediction_digest: str


class ModelEvaluation(Strict):
    candidate: str
    threshold: float
    clean_all: AlertMetrics
    clean_matched: AlertMetrics | None
    faulted: AlertMetrics | None
    detection_delta: float | None
    alarm_burden_delta: float | None
    pairs: list[MatchedOutcome]


class FaultEvaluation(Strict):
    version: Literal[1] = 1
    partition: Literal["out_of_fold"] = "out_of_fold"
    scenario_id: str
    scenario: FaultCase
    policy: FaultPolicy
    policy_fingerprint: str
    context_fingerprint: str
    source_digest: str
    data_hash: str
    config_fingerprint: str
    status: Literal["complete", "partial", "not_applicable"]
    expected_histories: int
    evaluated_histories: int
    exclusions: list[Exclusion]
    applications: list[HistoryApplication]
    models: list[ModelEvaluation] = Field(min_length=1, max_length=10)


def prediction_digest(scores, cycles) -> str:
    return hashlib.sha256(np.asarray(cycles, dtype="<i8").tobytes() + np.asarray(scores, dtype="<f8").tobytes()).hexdigest()


def checked_scores(candidate, design):
    design.assert_finite()
    scores = np.asarray(candidate.score(design), dtype=np.float64)
    if scores.shape != (len(design),) or not np.isfinite(scores).all():
        raise ValueError("Fitted model returned invalid prediction scores")
    return scores


class FixedDevelopmentEvaluator:
    def __init__(self, training, thresholds: dict[str, float], policy: FaultPolicy):
        self._policy = FaultPolicy.model_validate(policy.model_dump(mode="json"))
        self._validate_context(training, thresholds)
        # Keep the fitted context independent of later caller changes.
        self._training = deepcopy(training)
        # Rebuild cached row indices rather than copying potentially stale ones.
        self._training.dataset = replace(self._training.dataset)
        self._validate_context(self._training, thresholds)
        for fold in self._training.folds:
            fold.blocks = {}  # Unused training-time feature caches are not replay inputs.
        self._training.out_of_fold = {}
        self._thresholds = {name: float(thresholds[name]) for name in sorted(thresholds)}
        self._config = self._training.config
        self._source_digest = source_digest()
        fits = [(fold.fold_index, name, fold.candidates[name], fold.builder)
            for fold in self._training.folds for name in self._thresholds]
        self._context_fingerprint = fingerprint({"version": 1, "source": self._source_digest,
            "fits": joblib.hash(fits, hash_name="sha1"), "thresholds": self._thresholds,
            "data_hash": self._training.dataset.data_hash, "mapping": self._training.dataset.mapping.model_dump(mode="json"),
            "development_content": hashlib.sha256(self._training.dataset.frame.to_csv(index=False, float_format="%.17g").encode()).hexdigest(),
            "config": self._config.as_dict(), "splits": self._training.splits.model_dump(mode="json")})
        self._prepared = []
        self._clean = {name: {} for name in self._thresholds}
        self._clean_digests = {name: {} for name in self._thresholds}
        for fold in self._training.folds:
            blocks = engine_blocks(self._training.dataset, fold.builder, equipment_ids=fold.validation_engines)
            design = design_from_blocks(blocks, fold.builder.feature_names(), equipment_ids=fold.validation_engines)
            for name, threshold in self._thresholds.items():
                scores = checked_scores(fold.candidates[name], design)
                for equipment in fold.validation_engines:
                    mask = design.equipment_id == equipment
                    self._clean[name][equipment] = score_engine(equipment, scores[mask], design.cycle[mask], design.rul[mask], threshold, config=self._config)
                    self._clean_digests[name][equipment] = prediction_digest(scores[mask], design.cycle[mask])
            self._prepared.append((fold, blocks))
        self._cache: dict[str, FaultEvaluation] = {}
        self._evaluations = 0

    @property
    def thresholds(self):
        return dict(self._thresholds)

    @property
    def policy(self):
        return self._policy

    @property
    def config(self):
        return deepcopy(self._config)

    @property
    def context_fingerprint(self):
        return self._context_fingerprint

    @property
    def remaining_evaluations(self) -> int:
        """New (uncached) scenarios this evaluator can still execute."""
        return max(0, self.policy.max_evaluations - self._evaluations)

    def snapshot(self):
        return deepcopy(self._training)

    def cleanMetrics(self):
        return {name: aggregate(list(outcomes.values()), config=self._config) for name, outcomes in self._clean.items()}

    def is_cached(self, scenario_id: str) -> bool:
        return scenario_id in self._cache

    def _validate_context(self, training, thresholds):
        validate_splits(training.splits)
        config = training.config
        config.validate()
        if not config.exclude_failure_cycle:
            raise ValueError("Fixed evaluation requires failure-cycle exclusion")
        development = set(training.splits.development)
        if len(development) != len(training.splits.development) or not development:
            raise ValueError("Development histories must be nonempty and unique")
        if len(development) > self.policy.max_histories or len(training.dataset.frame) > self.policy.max_rows:
            raise ValueError("Development context exceeds the evaluation size limit")
        frame = training.dataset.frame
        columns = {"equipment_id", "cycle", "rul", "failure_cycle", *training.dataset.sensors}
        if not columns <= set(frame.columns) or not frame.columns.is_unique:
            raise ValueError("Development data does not match its canonical feature mapping")
        ids = frame["equipment_id"].to_numpy()
        if any(not isinstance(value, str) or not value for value in ids) or set(ids) != development:
            raise ValueError("Evaluator accepts development-only data; reserved or unexpected histories are forbidden")
        starts = np.r_[True, ids[1:] != ids[:-1]]
        if int(starts.sum()) != len(development):
            raise ValueError("Development histories must occupy contiguous feature blocks")
        for _, history in frame.groupby("equipment_id", sort=False):
            cycles = history["cycle"].to_numpy(dtype=float)
            rul = history["rul"].to_numpy(dtype=float)
            failure = history["failure_cycle"].to_numpy(dtype=float)
            if (not np.isfinite(np.concatenate([cycles, rul, failure])).all() or (cycles < 1).any()
                    or not np.equal(cycles, np.floor(cycles)).all() or not np.equal(rul, np.floor(rul)).all()
                    or not np.equal(np.diff(cycles), 1).all() or (rul < 0).any() or rul[-1] != 0
                    or not np.equal(failure, failure[0]).all() or not np.equal(cycles + rul, failure).all()):
                raise ValueError("Development feature histories must have consecutive cycles and complete failure targets")
        if config.fingerprint() != training.splits.config_fingerprint or config.fingerprint() != training.dataset.config.fingerprint():
            raise ValueError("Development configuration does not match its fitted split")
        if not 1 <= len(thresholds) <= 10 or not set(thresholds) <= set(training.specs):
            raise ValueError("Select between one and ten known fitted model thresholds")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in thresholds.values()):
            raise ValueError("Every fixed threshold must be finite")
        if not 2 <= len(training.folds) <= 10 or len(training.folds) != len(training.splits.folds):
            raise ValueError("Fitted fold count is outside the evaluation limit")
        if not set(self.policy.allowed_sensors) <= set(training.dataset.sensors):
            raise ValueError("Policy sensors are outside the fitted mapping")
        indices = set()
        for fold in training.folds:
            if fold.fold_index in indices or not 0 <= fold.fold_index < len(training.splits.folds):
                raise ValueError("Fitted fold identifiers must be unique and complete")
            indices.add(fold.fold_index)
            validation = set(fold.validation_engines)
            if (validation != set(training.splits.folds[fold.fold_index]) or len(validation) != len(fold.validation_engines)
                    or set(fold.train_engines) != development - validation or len(fold.train_engines) != len(set(fold.train_engines))):
                raise ValueError("Fitted fold membership leaks or disagrees with development assignments")
            if (type(fold.builder) is not FeatureBuilder or list(fold.builder.preprocessor.sensors) != training.dataset.sensors
                    or fold.builder.sensors != training.dataset.sensors or fold.builder.window != config.feature_window
                    or fold.builder.config.fingerprint() != config.fingerprint()
                    or np.asarray(fold.builder.preprocessor.medians).shape != (len(training.dataset.sensors),)
                    or np.asarray(fold.builder.preprocessor.stds).shape != (len(training.dataset.sensors),)
                    or not np.isfinite(fold.builder.preprocessor.medians).all()
                    or not np.isfinite(fold.builder.preprocessor.stds).all() or (fold.builder.preprocessor.stds < 0).any()):
                raise ValueError("Fitted fold preprocessing does not match the fixed context")
            if any(name not in fold.candidates or not fold.candidates[name].fitted or fold.candidates[name].name != name for name in thresholds):
                raise ValueError("Every selected model must already be fitted in every fold")

    def evaluate(self, case: FaultCase, *, cancelled=None) -> FaultEvaluation:
        case = FaultCase.model_validate(case.model_dump(mode="json"))
        self.policy.check(case, self._config)
        deadline = time.monotonic() + self.policy.max_seconds

        def check():
            if (cancelled is not None and cancelled()) or time.monotonic() >= deadline:
                raise EvaluationStopped("Evaluation cancelled or cooperative time limit reached")

        check()
        if case.scenario_id in self._cache:
            return self._cache[case.scenario_id].model_copy(deep=True)
        if self._evaluations >= self.policy.max_evaluations:
            raise EvaluationStopped("Investigation evaluation budget exhausted")
        self._evaluations += 1  # Failed executions consume a slot too.
        scored = {name: {} for name in self._thresholds}
        digests = {name: {} for name in self._thresholds}
        exclusions, applications = [], []
        for fold, blocks in self._prepared:
            faulted = {}
            for equipment in fold.validation_engines:
                check()
                block = blocks[equipment]
                injection = apply_case(self._training.dataset.sensor_matrix(equipment), block.rul, case, fold.builder, self._config)
                if not injection.applied:
                    exclusions.append(Exclusion(equipment_id=equipment, reasons=list(injection.reasons)))
                    continue
                features = block.features.copy()
                for atom in case.components:
                    index = fold.builder.preprocessor.index_of(atom.sensor)
                    fold.builder.rebuild_sensor(features, injection.values[:, index], atom.sensor)
                if any(np.array_equal(features[block.scorable, fold.builder.block(atom.sensor)],
                        block.features[block.scorable, fold.builder.block(atom.sensor)], equal_nan=True) for atom in case.components):
                    exclusions.append(Exclusion(equipment_id=equipment, reasons=["A component changed no scorable features"]))
                    continue
                faulted[equipment] = EngineBlock(equipment, features, block.labels, block.cycles, block.rul, block.rows, block.scorable)
                applications.append(HistoryApplication(equipment_id=equipment, components=list(injection.components)))
            if not faulted:
                continue
            design = design_from_blocks(faulted, fold.builder.feature_names())
            for name, threshold in self._thresholds.items():
                check()
                scores = checked_scores(fold.candidates[name], design)
                check()
                for equipment in faulted:
                    mask = design.equipment_id == equipment
                    scored[name][equipment] = score_engine(equipment, scores[mask], design.cycle[mask], design.rul[mask], threshold, config=self._config)
                    digests[name][equipment] = prediction_digest(scores[mask], design.cycle[mask])
        models = []
        for name, threshold in self._thresholds.items():
            equipment = sorted(scored[name])
            clean = aggregate([self._clean[name][e] for e in equipment], config=self._config) if equipment else None
            faulted = aggregate([scored[name][e] for e in equipment], config=self._config) if equipment else None
            models.append(ModelEvaluation(candidate=name, threshold=threshold,
                clean_all=aggregate(list(self._clean[name].values()), config=self._config), clean_matched=clean, faulted=faulted,
                detection_delta=faulted.detection_fraction - clean.detection_fraction if faulted else None,
                alarm_burden_delta=(faulted.early_alarm_burden - clean.early_alarm_burden
                    if faulted and faulted.early_alarm_burden is not None and clean.early_alarm_burden is not None else None),
                pairs=[MatchedOutcome(equipment_id=e, clean=self._clean[name][e].outcome, faulted=scored[name][e].outcome,
                    clean_prediction_digest=self._clean_digests[name][e], faulted_prediction_digest=digests[name][e]) for e in equipment]))
        check()
        count, expected = len(applications), len(self._training.splits.development)
        result = FaultEvaluation(scenario_id=case.scenario_id, scenario=case, policy=self.policy,
            policy_fingerprint=self.policy.fingerprint, context_fingerprint=self.context_fingerprint,
            source_digest=self._source_digest, data_hash=self._training.dataset.data_hash, config_fingerprint=self._config.fingerprint(),
            status="complete" if count == expected else "partial" if count else "not_applicable",
            expected_histories=expected, evaluated_histories=count, exclusions=exclusions, applications=applications, models=models)
        self._cache[case.scenario_id] = result.model_copy(deep=True)
        return result.model_copy(deep=True)
