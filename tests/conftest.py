from pathlib import Path

import pytest
from app.config import reset_settings


@pytest.fixture
def local_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("SIDEKICK_MODE", "full")
    monkeypatch.setenv("SIDEKICK_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("SIDEKICK_MLFLOW", "0")
    monkeypatch.setenv("SIDEKICK_BUNDLE_PATH", str(Path(__file__).resolve().parents[1] / "evidence" / "bundle.json"))
    reset_settings()
    from app.api.deps import _cached_bundle
    _cached_bundle.cache_clear()
    yield tmp_path
    reset_settings()
    _cached_bundle.cache_clear()
