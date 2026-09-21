"""Shared fixtures.

Every fixture uses the synthetic generator rather than C-MAPSS, so the suite runs
on a fresh clone with no download and no network.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from app.config import EXPERIMENT, reset_settings
from app.data import make_synthetic_dataset
from app.features.build import FeatureBuilder, Preprocessor
from app.models.splits import make_splits

#: Small enough to keep the suite quick, large enough to exercise grouped folds.
TEST_CONFIG = replace(
    EXPERIMENT,
    holdout_engines=4,
    n_folds=3,
    configs_per_candidate=1,
    feature_window=10,
)


@pytest.fixture(scope="session")
def config():
    TEST_CONFIG.validate()
    return TEST_CONFIG


@pytest.fixture(scope="session")
def dataset(config):
    return make_synthetic_dataset(
        n_equipment=18, min_life=110, max_life=170, config=config
    )


@pytest.fixture(scope="session")
def preprocessor(dataset):
    return Preprocessor.fit(dataset)


@pytest.fixture(scope="session")
def builder(preprocessor, config):
    return FeatureBuilder(preprocessor, config)


@pytest.fixture(scope="session")
def splits(dataset, config):
    return make_splits(dataset, config)


@pytest.fixture(scope="session")
def evaluation(dataset, config):
    """A complete development evaluation on the synthetic dataset."""
    from app.scoring.pipeline import evaluate

    return evaluate(
        dataset,
        config=config,
        include_full_matrix=False,
        fault_sensors=["temp_bearing", "vibration_rms"],
        augmentation_copies=1,
    )


@pytest.fixture(scope="session")
def bundle(evaluation, config, tmp_path_factory):
    """A bundle carrying run records, as a real one does."""
    from app.evidence.bundle import build_bundle
    from app.evidence.store import EvidenceStore

    store = EvidenceStore(tmp_path_factory.mktemp("runs"))
    training = store.start_run(
        "training", config=config, data_hash=evaluation.profile.data_hash
    )
    store.log_metrics(training, {"engines": float(evaluation.profile.equipment_count)})

    recommended = evaluation.selection.recommended or evaluation.selection.ranked[0]
    selection = store.start_run(
        "selection",
        config=config,
        data_hash=evaluation.profile.data_hash,
        parent_run_id=training.run_id,
        params={"outcome": evaluation.selection.outcome.value},
    )
    store.log_metrics(
        selection, {"clean_detection_fraction": recommended.clean.detection_fraction}
    )

    return build_bundle(
        evaluation, config=config, runs=store.list_runs(), replay_engines=2
    )


@pytest.fixture(scope="session")
def bundle_path(bundle, tmp_path_factory) -> Path:
    from app.utils.jsonio import write_json

    path = tmp_path_factory.mktemp("evidence") / "bundle.json"
    write_json(path, bundle.model_dump(mode="json"))
    return path


@pytest.fixture
def client(bundle_path, monkeypatch):
    """A test client over the replay-mode API, backed by the fixture bundle."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("SIDEKICK_MODE", "replay")
    monkeypatch.setenv("SIDEKICK_BUNDLE_PATH", str(bundle_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    # Point the static directory at nothing, so these tests exercise the API and do
    # not change behaviour depending on whether the frontend happens to be built.
    monkeypatch.setenv("SIDEKICK_STATIC_DIR", str(bundle_path.parent / "no-frontend"))
    reset_settings()

    from app.api.deps import reload_bundle
    from app.main import create_app

    reload_bundle()
    with TestClient(create_app()) as test_client:
        yield test_client
    reload_bundle()
    reset_settings()


@pytest.fixture
def registry(bundle):
    from app.copilot.tools import ToolRegistry

    return ToolRegistry(bundle)
