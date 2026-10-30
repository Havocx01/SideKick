import importlib.util
import json
from pathlib import Path


def test_one_command_demo_discovers_reduces_remedies_and_exports(tmp_path, capsys):
    spec = importlib.util.spec_from_file_location("demo_cli", Path(__file__).resolve().parents[1] / "scripts/demo_investigation.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    assert cli.main(["--root", str(tmp_path / "investigations"), "--output", str(tmp_path / "public.json")]) == 0
    printed = capsys.readouterr().out
    assert "Measured failure: oil_particles:stuck+vibration_rms:stuck" in printed and "Replay matches: True" in printed
    assert "Reduced (complete): oil_particles stuck from" in printed and "Not a proof of a global minimum." in printed
    assert "Remedy threshold 0.5: improved" in printed and "degraded 0" in printed
    evidence = json.loads((tmp_path / "public.json").read_text())
    assert evidence["discoveryFamilies"] == ["oil_particles:stuck+vibration_rms:stuck"] and evidence["reductions"] and evidence["remedies"]
    assert "fragile threshold" not in json.dumps(evidence) and evidence["reproduction"]["public"]
    assert (tmp_path / "investigations/contexts/demo-fragile-threshold/manifest.json").is_file()
    assert cli.main(["--root", str(tmp_path / "investigations"), "--output", str(tmp_path / "again.json")]) == 0
