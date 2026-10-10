"""Git checkout/archive must preserve checksum-bound recorded evidence."""

import hashlib
import io
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from app.evidence.bundle import load_bundle
from app.evidence.supplement import attach_replays

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("autocrlf", ["false", "true"])
def test_git_checkout_and_archive_keep_verified_replay_bytes(tmp_path, autocrlf):
    git = shutil.which("git")
    if git is None:
        pytest.skip("Git is needed to verify repository packaging")

    def command(*args):
        return subprocess.check_output([git, *args], cwd=tmp_path)

    command("init", "--quiet")
    command("config", "core.autocrlf", autocrlf)
    (tmp_path / ".gitattributes").write_bytes((ROOT / ".gitattributes").read_bytes())
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    for name in ("bundle.json", "replays-v1.5.json"):
        (evidence / name).write_bytes((ROOT / "evidence" / name).read_bytes())
    original = (evidence / "bundle.json").read_bytes()
    expected = json.loads((evidence / "replays-v1.5.json").read_text())["original_bundle_sha256"]
    assert hashlib.sha256(original).hexdigest() == expected
    command("add", ".gitattributes", "evidence")
    command("diff", "--cached", "--check", "--", "evidence/bundle.json")
    blob = command("show", ":evidence/bundle.json")
    assert blob == original, "Git normalized bytes bound to the replay checksum"
    tree = command("write-tree").decode().strip()
    with zipfile.ZipFile(io.BytesIO(command("archive", "--format=zip", tree))) as archive:
        assert archive.read("evidence/bundle.json") == original

    checkout = tmp_path / "checkout"
    checkout.mkdir()
    command("-c", "core.autocrlf=false", "checkout-index", "--all", f"--prefix={checkout.as_posix()}/")
    path = checkout / "evidence/bundle.json"
    assert path.read_bytes() == original
    bundle = load_bundle(path)
    before = len(bundle.replay_series)
    metrics = [row.model_dump_json() for row in bundle.scenario_results]
    attach_replays(bundle, path)
    assert len(bundle.replay_series) > before
    assert any(row.config_id == "lr2" for row in bundle.replay_series)
    assert [row.model_dump_json() for row in bundle.scenario_results] == metrics


def test_mismatched_replay_checksum_is_still_rejected(tmp_path):
    for name in ("bundle.json", "replays-v1.5.json"):
        (tmp_path / name).write_bytes((ROOT / "evidence" / name).read_bytes())
    path = tmp_path / "bundle.json"
    bundle = load_bundle(path)
    before = bundle.model_dump_json()
    # Whitespace remains valid JSON but changes its exact evidence fingerprint.
    path.write_bytes(path.read_bytes() + b" ")
    attach_replays(bundle, path)
    assert bundle.model_dump_json() == before
