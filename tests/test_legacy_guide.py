from types import SimpleNamespace

from app.copilot.fallback import _metric_answer


def test_legacy_metrics_answer_handles_unavailable_burden(monkeypatch):
    rows = {"results": [{"candidate": "example", "metrics": {"detected": 1, "engines": 1, "late": 0,
        "missed": 0, "detection_fraction": 1, "detection_ci_lower": .2, "detection_ci_upper": 1,
        "early_alarm_burden": None, "median_lead_time": 20}}]}
    monkeypatch.setattr("app.copilot.fallback._invoke", lambda *args: (rows, SimpleNamespace()))
    answer, _, _ = _metric_answer(None)
    assert "example" in answer and "None" not in answer
