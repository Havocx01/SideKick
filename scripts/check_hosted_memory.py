"""Run inside a Linux demo container; test its sample and measure whole-container memory."""

import csv
import io
import json
import threading
import time
import zipfile
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener


def main():
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    base = "http://127.0.0.1:8000"

    def request(path, payload=None):
        body = json.dumps(payload).encode() if payload is not None else None
        with opener.open(Request(base + path, data=body, headers={"Content-Type": "application/json", "X-Sidekick-Request": "1", "Origin": base}), timeout=30) as response:
            return response.read()

    def api(path, payload=None):
        return json.loads(request(path, payload))

    health = None
    for attempt in range(30):
        try:
            health = api("/api/health")
            break
        except URLError:
            time.sleep(1)
    assert health is not None, "The demo server did not become ready"
    assert health["mode"] == "demo" and not health["can_upload"] and not health["can_validate"]
    peak = {"working_set_bytes": 0, "container_current_bytes": 0}
    stop = threading.Event()

    def sample_memory():
        while not stop.wait(.05):
            root = Path("/sys/fs/cgroup")
            current = int((root / "memory.current").read_text())
            stats = dict(line.split() for line in (root / "memory.stat").read_text().splitlines())
            working = current - int(stats.get("inactive_file", 0))
            peak["working_set_bytes"] = max(peak["working_set_bytes"], working)
            peak["container_current_bytes"] = max(peak["container_current_bytes"], current)

    monitor = threading.Thread(target=sample_memory)
    monitor.start()
    started = time.monotonic()
    try:
        dataset = api("/api/datasets/sample", {})
        job = api("/api/experiments", {"dataset_id": dataset["dataset_id"]})
        id = job["experiment_id"]
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            job = api(f"/api/experiments/{id}")
            if job["status"] not in ("queued", "running", "cancelling"):
                break
            time.sleep(.2)
        assert job["status"] == "completed", job
        api(f"/api/decision?experiment_id={id}")
        api(f"/api/replay/index?experiment_id={id}")
        request(f"/api/export/report?experiment_id={id}")
        with zipfile.ZipFile(io.BytesIO(request(f"/api/export?experiment_id={id}"))) as archive:
            evidence = json.loads(archive.read("evidence.json"))
            rows = list(csv.DictReader(io.StringIO(archive.read("metrics.csv").decode())))
            assert len(rows) == len(evidence["scenario_results"])
            assert evidence["final_evaluation"] is None
        isolated = build_opener(HTTPCookieProcessor(CookieJar()))
        try:
            isolated.open(base + f"/api/experiments/{id}")
            raise AssertionError("A second browser accessed another browser's experiment")
        except HTTPError as error:
            assert error.code == 404
    finally:
        stop.set()
        monitor.join()
    result = {"release": health["version"], "elapsed_seconds": round(time.monotonic() - started, 2),
        "experiment_id": id, "peak_working_set_mib": round(peak["working_set_bytes"] / 2**20, 2),
        "peak_sampled_container_mib": round(peak["container_current_bytes"] / 2**20, 2),
        "cgroup_peak_mib": round(int(Path("/sys/fs/cgroup/memory.peak").read_text()) / 2**20, 2),
        "measurement": "50 ms cgroup v2 sampling; working set = current minus inactive_file; includes monitor, server and worker",
        "source_digest": evidence["source_digest"], "dependency_versions": evidence["dependency_versions"],
        "below_450_mib": peak["working_set_bytes"] < 450 * 2**20}
    print(json.dumps(result, indent=2))
    assert result["below_450_mib"], "Hosted working set exceeds the 450 MiB target"


if __name__ == "__main__":
    main()
