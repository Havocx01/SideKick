import importlib.util
import json
from pathlib import Path


def test_one_command_demo_discovers_reduces_remedies_and_exports(tmp_path, capsys):
    spec = importlib.util.spec_from_file_location("demo_cli", Path(__file__).resolve().parents[1] / "scripts/demo_investigation.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    assert cli.main(["--root", str(tmp_path / "investigations"), "--output", str(tmp_path / "public.json")]) == 0
    printed = capsys.readouterr().out
    assert "Measured failure (hand-authored or seeded): oil_particles:stuck+vibration_rms:stuck" in printed and "Replay matches: True" in printed
    assert "warning threshold 0.95 is deliberately fragile" in printed and "chosen by Nemotron" not in printed
    assert "Reduced (complete): oil_particles stuck from" in printed and "Not a proof of a global minimum." in printed
    assert "Remedy threshold 0.5: improved" in printed and "degraded 0" in printed
    evidence = json.loads((tmp_path / "public.json").read_text())
    assert evidence["discoveryFamilies"] == ["oil_particles:stuck+vibration_rms:stuck"] and evidence["reductions"] and evidence["remedies"]
    assert "Demo: find sensor faults" not in json.dumps(evidence) and evidence["reproduction"]["public"]
    assert evidence["demonstration"]["threshold"] == .95 and "deliberately fragile" in evidence["demonstration"]["note"]
    assert {row["chosenBy"] for row in evidence["experiments"]} == {"supplied"} and evidence["controller"] is None
    assert len(list((tmp_path / "investigations/contexts").glob("demo-fragile-threshold-*/manifest.json"))) == 1
    assert cli.main(["--root", str(tmp_path / "investigations"), "--output", str(tmp_path / "again.json")]) == 0


def test_demo_with_nemotron_marks_its_cases_and_reduces_one_it_chose(tmp_path, capsys, monkeypatch):
    from app.config import Settings
    from app.faults.profiles import loadPolicy
    from test_nemotron_controller import provider, stop
    spec = importlib.util.spec_from_file_location("demo_agent_cli", Path(__file__).resolve().parents[1] / "scripts/demo_investigation.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    cli.get_settings = lambda: Settings(mode="full", assistant_provider="nebius", assistant_model="nvidia/nemotron-3-super-120b-a12b",
        nebius_api_key="mock", nebius_reasoning_tokens=0, assistant_live_enabled=True)
    alias = {sensor: f"channel-{index}" for index, sensor in enumerate(loadPolicy("synthetic-rotating-v1").allowed_sensors, 1)}
    stuck = [{"kind": "stuck", "sensor": alias[sensor], "onset": {"mode": "explicit", "onset_before_failure": 50}, "duration": {"mode": "persistent"}}
        for sensor in ("vibration_rms", "oil_particles")]
    chosen = {"proposal": {"scenario": {"components": stuck}, "reason": "Refine the measured stuck pair.",
        "hypothesis": {"suspected": "A later onset still costs warnings.", "supportIf": "Warnings are lost.", "weakenIf": "Warnings hold.", "basedOn": ["result-1"]}},
        "stopReason": None}
    provider(monkeypatch, [chosen, stop()])
    assert cli.main(["--root", str(tmp_path / "investigations"), "--output", str(tmp_path / "public.json"), "--allow-nebius", "--max-provider-calls", "2"]) == 0
    printed = capsys.readouterr().out
    assert "Nemotron: 2 calls, stop model_stopped" in printed and "chosen by Nemotron" in printed
    assert "Measured failure (Nemotron): oil_particles:stuck+vibration_rms:stuck" in printed
    evidence = json.loads((tmp_path / "public.json").read_text())
    assert [row["chosenBy"] for row in evidence["experiments"]].count("nemotron") == 1 and evidence["controller"]["adaptation"][0]["basedOn"] == ["result-1"]
