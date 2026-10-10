"""Exercise the actual Windows entry point without using the saved workspace."""

import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell entry point")
@pytest.mark.parametrize("shell", ["pwsh", "powershell"])
def test_api_task_stays_running_until_explicit_stop(tmp_path, shell):
    powershell = shutil.which(shell)
    if not powershell:
        pytest.skip(f"{shell} is not installed")
    # Separate port and workspace: never interrupt or modify a user's server.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = os.environ.copy()
    env.update({
        "SIDEKICK_MODE": "full",
        "SIDEKICK_ARTIFACTS_DIR": str(tmp_path / "artifacts"),
        "SIDEKICK_DATA_DIR": str(tmp_path / "data"),
        "SIDEKICK_BUNDLE_PATH": str(ROOT / "evidence/bundle.json"),
        "SIDEKICK_STATIC_DIR": str(ROOT / "frontend/dist"),
        "SIDEKICK_ASSISTANT_LIVE_ENABLED": "0",
        "SIDEKICK_MLFLOW": "0",
    })
    http = build_opener(ProxyHandler({}))
    url = f"http://127.0.0.1:{port}"
    log = tmp_path / "api-task.log"
    with log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
             str(ROOT / "tasks.ps1"), "api", "-Port", str(port)],
            cwd=tmp_path, env=env, stdout=output, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        try:
            deadline = time.monotonic() + 45
            while True:
                assert process.poll() is None, log.read_text(encoding="utf-8")
                try:
                    with http.open(url + "/api/health", timeout=2) as response:
                        assert json.load(response)["status"] == "ok"
                    break
                except URLError:
                    assert time.monotonic() < deadline, log.read_text(encoding="utf-8")
                    time.sleep(.25)
            # Keep requesting data past the reported few-second shutdown window.
            for _ in range(12):
                with http.open(url + "/api/experiments", timeout=2) as response:
                    assert json.load(response) == []
                assert process.poll() is None
                time.sleep(1)
            with http.open(url + "/", timeout=2) as response:
                assert response.status == 200
            recorded = log.read_text(encoding="utf-8")
            assert recorded.count("Started server process") == 1
            assert "reloader process" not in recorded
            assert "Shutting down" not in recorded
            # A second launch must report its failed bind, not silently return success.
            collision_env = {**env, "SIDEKICK_ARTIFACTS_DIR": str(tmp_path / "collision")}
            collision = subprocess.run(
                [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                 str(ROOT / "tasks.ps1"), "api", "-Port", str(port)],
                cwd=tmp_path, env=collision_env, capture_output=True, text=True, timeout=45,
            )
            assert collision.returncode != 0
            assert "Sidekick server exited with code" in collision.stderr
            with http.open(url + "/api/health", timeout=2) as response:
                assert json.load(response)["status"] == "ok"
        finally:
            if process.poll() is None:
                # This signal targets only the test-created console group.
                process.send_signal(signal.CTRL_BREAK_EVENT)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                process.wait(timeout=5)
    recorded = log.read_text(encoding="utf-8")
    assert "Application shutdown complete" in recorded
