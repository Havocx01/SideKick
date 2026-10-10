"""Prepare the local app, open its current UI and serve it with one command."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
LOCAL_HTTP = build_opener(ProxyHandler({}))
IGNORED = {"node_modules", "dist", ".vite", "test-results", "playwright-report", "__pycache__"}


def fingerprint(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def frontend_fingerprint() -> str:
    files = []
    for directory, folders, names in os.walk(ROOT / "frontend"):
        folders[:] = [name for name in folders if name not in IGNORED]
        files.extend(Path(directory) / name for name in names)
    files.extend([ROOT / "scripts/generate_types.py", ROOT / "backend/app/schemas.py",
                  ROOT / "backend/app/assistant/schemas.py"])
    files.extend((ROOT / "backend").glob("requirements*.txt"))
    return fingerprint(files)


def output_fingerprint() -> str:
    return fingerprint([p for p in (ROOT / "frontend/dist").rglob("*")
                        if p.is_file() and p.name != ".sidekick-build.json"])


def read_state(path: Path) -> dict:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def run(command: list[str], label: str, *, cwd: Path = ROOT) -> None:
    print("\n" + label, flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def supported_node(version: str) -> bool:
    try:
        major, minor, _patch = map(int, version.strip().lstrip("v").split("."))
        return (major == 20 and minor >= 19) or (major == 22 and minor >= 12) or major >= 23
    except ValueError:
        return False


def prepare() -> Path:
    if sys.version_info < (3, 11):
        raise RuntimeError("Install Python 3.11 or newer, then launch Sidekick again.")
    node = shutil.which("node")
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not node or not npm:
        raise RuntimeError("Install Node.js LTS from https://nodejs.org/en/download, then launch Sidekick again.")
    version = subprocess.check_output([node, "--version"], text=True).strip()
    if not supported_node(version):
        raise RuntimeError("Update Node.js to LTS (22.12+ or 20.19+), then launch Sidekick again.")

    venv = ROOT / ".venv"
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        run([sys.executable, "-m", "venv", str(venv)], "First launch: preparing your local workspace...")
    state_file = venv / ".sidekick-setup.json"
    requirements = fingerprint([ROOT / "backend/requirements.txt", ROOT / "backend/requirements-train.txt"])
    if read_state(state_file).get("requirements") != requirements:
        run([str(python), "-m", "pip", "install", "-r", str(ROOT / "backend/requirements-train.txt")],
            "Installing Sidekick dependencies. First launch may take a few minutes...")
        state_file.write_text(json.dumps({"requirements": requirements}), encoding="utf-8")

    build_state = ROOT / "frontend/dist/.sidekick-build.json"
    saved = read_state(build_state)
    if (not (ROOT / "frontend/dist/index.html").is_file()
            or saved.get("source") != frontend_fingerprint()
            or saved.get("output") != output_fingerprint()):
        run([str(python), str(ROOT / "scripts/generate_types.py")], "Preparing the latest interface...")
        frontend = ROOT / "frontend"
        npm_state = frontend / "node_modules/.sidekick-dependencies.json"
        packages = fingerprint([frontend / "package.json", frontend / "package-lock.json"])
        if read_state(npm_state).get("packages") != packages:
            run([npm, "ci", "--no-audit", "--no-fund"], "Installing the interface dependencies...", cwd=frontend)
            npm_state.write_text(json.dumps({"packages": packages}), encoding="utf-8")
        run([npm, "run", "build"], "Building the latest interface...", cwd=frontend)
        build_state.write_text(json.dumps({"source": frontend_fingerprint(), "output": output_fingerprint()}), encoding="utf-8")
    else:
        print("Your installation and interface are up to date.", flush=True)
    return python


def current_ui(url: str) -> bool:
    try:
        with LOCAL_HTTP.open(url + "/api/health", timeout=2) as response:
            health = json.load(response)
        if not isinstance(health, dict) or health.get("status") != "ok" or health.get("mode") != "full":
            return False
        with LOCAL_HTTP.open(url + "/", timeout=2) as response:
            return response.read() == (ROOT / "frontend/dist/index.html").read_bytes()
    except (OSError, ValueError, URLError):
        return False


def port_in_use(port: int) -> bool:
    with socket.socket() as connection:
        connection.settimeout(1)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8140)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, interrupt)
    server = None
    try:
        python = prepare()
        url = f"http://127.0.0.1:{args.port}"
        if port_in_use(args.port):
            if not current_ui(url):
                raise RuntimeError(f"Port {args.port} is in use by another app or an older Sidekick. "
                                   "Close that app's server window, then launch Sidekick again.")
            print(f"Sidekick is already running: {url}", flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            return 0

        env = os.environ.copy()
        env["SIDEKICK_MODE"] = "full"
        env["SIDEKICK_STATIC_DIR"] = str(ROOT / "frontend/dist")
        env.setdefault("SIDEKICK_MLFLOW", "0")
        command = [str(python), "-m", "uvicorn", "app.main:app", "--app-dir", str(ROOT / "backend"),
                   "--host", "127.0.0.1", "--port", str(args.port)]
        if (ROOT / ".env").is_file():
            command.extend(["--env-file", str(ROOT / ".env")])
        print("\nStarting Sidekick. Keep this window open; press Ctrl+C to stop.\n", flush=True)
        server = subprocess.Popen(command, cwd=ROOT, env=env)
        deadline = time.monotonic() + 45
        while server.poll() is None and time.monotonic() < deadline:
            if current_ui(url):
                print(f"\nSidekick is ready: {url}\n", flush=True)
                if not args.no_browser:
                    webbrowser.open(url)
                return server.wait()
            time.sleep(.25)
        raise RuntimeError("Sidekick did not become ready. Check the server messages above, then try again.")
    except KeyboardInterrupt:
        print("\nSidekick stopped.", flush=True)
        return 0
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"\nCould not launch Sidekick: {error}", file=sys.stderr, flush=True)
        return 1
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


def interrupt(_signal, _frame) -> None:
    raise KeyboardInterrupt


if __name__ == "__main__":
    raise SystemExit(main())
