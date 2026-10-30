import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from app.faults.remote import runJob


@pytest.fixture
def checker(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "scripts/check_worker_image.py"
    spec = importlib.util.spec_from_file_location("worker_check", source)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    work = tmp_path / "jobs"
    work.mkdir()
    monkeypatch.setattr(cli.tempfile, "mkdtemp", lambda **kwargs: str(work))
    return cli, work


@pytest.mark.parametrize("tamper", [False, True])
def test_container_check_uses_one_image_and_requires_exact_results(checker, monkeypatch, capsys, tamper):
    cli, work = checker
    original = subprocess.run
    calls = []
    def run(command, **kwargs):
        if command[0] != "docker":
            return original(command, **kwargs)
        calls.append(command)
        if "--prepare" in command:
            cli.prepare(work)
        else:
            result = runJob(work / "outbox/job.json", work / "context", work / "inbox", trusted=True)
            if tamper:
                payload = json.loads(result.read_text(encoding="utf-8"))
                payload["evaluation"]["models"][0]["threshold"] += .01
                result.write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(cli.subprocess, "run", run)
    assert cli.main(["--image", "same-runtime"]) == int(tamper)
    assert len(calls) == 2 and all("same-runtime" in command for command in calls)
    assert all(command[command.index("--network") + 1] == "none" and "--rm" in command for command in calls)
    assert "--prepare" in calls[0] and "--trust-local-artifact" in calls[1]
    assert calls[1][-4:] == ["--cpu-seconds", "300", "--memory-mb", "2048"]
    if not tamper:
        assert "matches container coordinator evaluation" in capsys.readouterr().out


def test_local_command_check_still_runs_real_replay(checker, capsys):
    cli, work = checker
    assert cli.main(["--command", f'"{sys.executable}" scripts/run_fault_job.py']) == 0
    assert "matches local evaluation" in capsys.readouterr().out
    assert (work / "expected.json").is_file()


def test_container_directories_are_writable_before_preparation(checker, monkeypatch):
    cli, work = checker
    modes = {}
    monkeypatch.setattr(Path, "chmod", lambda path, mode: modes.update({path: mode}))
    def inspect(command, **kwargs):
        assert all(modes.get(path) == 0o777 for path in (work, work / "outbox", work / "inbox"))
        raise RuntimeError("permissions inspected")
    monkeypatch.setattr(cli.subprocess, "run", inspect)
    with pytest.raises(RuntimeError, match="permissions inspected"):
        cli.main(["--image", "same-runtime"])
