import csv
import io
import json
import zipfile
from pathlib import Path

import pytest
from app.evidence.bundle import load_bundle
from app.experiments.decision import decision
from app.experiments.export import export_zip


@pytest.fixture
def benchmark():
    return load_bundle(Path(__file__).resolve().parents[1] / "evidence" / "bundle.json")


def test_guide_explains_inspected_candidate(benchmark):
    report = decision(benchmark, "logistic_regression/lr2")
    assert report.inspected_candidate == "logistic_regression/lr2"
    assert "does not meet" in report.title
    assert "41/80" in report.fault_summary
    assert all("candidate=logistic_regression%2Flr2" in item.link for item in report.guide)
    with pytest.raises(ValueError):
        decision(benchmark, "missing/model")


def test_export_preserves_metrics_and_redacts_sensor_values(benchmark):
    before = benchmark.model_dump_json()
    with zipfile.ZipFile(io.BytesIO(export_zip(benchmark, "logistic_regression/lr2"))) as archive:
        metrics = list(csv.DictReader(io.StringIO(archive.read("metrics.csv").decode())))
        source = json.loads(archive.read("provenance.json"))
        evidence = json.loads(archive.read("evidence.json"))
        assert source["report_candidate"] == "logistic_regression/lr2"
        assert len(metrics) == len(benchmark.scenario_results)
        assert all(p["sensor_clean"] is None and p["sensor_faulted"] is None for s in evidence["replay_series"] for p in s["points"])
        assert "data.csv" not in archive.namelist()
        assert "Logistic regression (lr2) does not meet" in archive.read("decision-report.html").decode()
    assert benchmark.model_dump_json() == before
