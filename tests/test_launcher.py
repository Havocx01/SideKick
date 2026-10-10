"""The launcher must never silently open a stale frontend or another service."""

import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

spec = importlib.util.spec_from_file_location("sidekick_launcher", Path(__file__).resolve().parents[1] / "scripts/launch.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


@pytest.mark.parametrize("version, supported", [
    ("v20.18.0", False), ("v20.19.0", True), ("v21.7.0", False),
    ("v22.11.0", False), ("v22.12.0", True), ("v24.21.0", True), ("broken", False),
])
def test_node_runtime_minimum(version, supported):
    assert launcher.supported_node(version) == supported


def test_build_fingerprint_detects_changes_but_ignores_installed_packages(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    for name in ["frontend/src/main.tsx", "frontend/node_modules/package/index.js",
                 "frontend/dist/index.html", "scripts/generate_types.py", "backend/app/schemas.py",
                 "backend/app/assistant/schemas.py", "backend/requirements.txt"]:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("original")
    original = launcher.frontend_fingerprint()
    (tmp_path / "frontend/node_modules/package/index.js").write_text("installed change")
    (tmp_path / "frontend/dist/index.html").write_text("output change")
    assert launcher.frontend_fingerprint() == original
    (tmp_path / "frontend/src/main.tsx").write_text("new UI")
    assert launcher.frontend_fingerprint() != original


def test_missing_or_damaged_assets_invalidate_the_build(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    assets = tmp_path / "frontend/dist/assets"
    assets.mkdir(parents=True)
    chunk = assets / "lazy.js"
    chunk.write_text("current UI")
    original = launcher.output_fingerprint()
    (assets.parent / ".sidekick-build.json").write_text("metadata")
    assert launcher.output_fingerprint() == original
    chunk.unlink()
    assert launcher.output_fingerprint() != original


def test_an_occupied_port_never_opens_a_different_ui(monkeypatch):
    monkeypatch.setattr(launcher, "prepare", lambda: Path("python"))
    monkeypatch.setattr(launcher, "port_in_use", lambda port: True)
    monkeypatch.setattr(launcher, "current_ui", lambda url: False)
    opened = []
    monkeypatch.setattr(launcher.webbrowser, "open", opened.append)
    monkeypatch.setattr(launcher.sys, "argv", ["launch.py"])
    assert launcher.main() == 1
    assert opened == []


def test_failed_setup_never_starts_a_server_or_opens_a_browser(monkeypatch):
    def fail():
        raise subprocess.CalledProcessError(2, ["npm", "run", "build"])
    monkeypatch.setattr(launcher, "prepare", fail)
    started = []
    opened = []
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *args, **kwargs: started.append(args))
    monkeypatch.setattr(launcher.webbrowser, "open", opened.append)
    monkeypatch.setattr(launcher.sys, "argv", ["launch.py"])
    assert launcher.main() == 1
    assert started == opened == []


def test_existing_current_ui_opens_without_starting_another_server(monkeypatch):
    monkeypatch.setattr(launcher, "prepare", lambda: Path("python"))
    monkeypatch.setattr(launcher, "port_in_use", lambda port: True)
    monkeypatch.setattr(launcher, "current_ui", lambda url: True)
    opened = []
    monkeypatch.setattr(launcher.webbrowser, "open", opened.append)
    monkeypatch.setattr(launcher.sys, "argv", ["launch.py"])
    assert launcher.main() == 0
    assert opened == ["http://127.0.0.1:8140"]


def test_corrupt_installation_marker_requires_setup_again(tmp_path):
    marker = tmp_path / "state.json"
    marker.write_text("unfinished")
    assert launcher.read_state(marker) == {}
    marker.write_text(json.dumps({"requirements": "ready"}))
    assert launcher.read_state(marker) == {"requirements": "ready"}
