"""Offline review packets retain evidence scope without inventing a study."""
import csv
import hashlib
import importlib.util
import json
import socket
from html.parser import HTMLParser
from pathlib import Path

import pytest

from app.evidence.bundle import load_bundle

ROOT = Path(__file__).resolve().parents[1]


class Links(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.hrefs = []
        self.feed(text)

    def handle_starttag(self, tag, attributes):
        if tag == "a":
            self.hrefs.extend(value for name, value in attributes if name == "href")


@pytest.fixture
def generator():
    spec = importlib.util.spec_from_file_location("engineer_pack", ROOT / "scripts/prepare_engineer_evaluation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def packet(generator, tmp_path, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("An offline packet must not open a network connection.")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setenv("OPENAI_API_KEY", "secret-test-marker-never-export")
    monkeypatch.setenv("SIDEKICK_ASSISTANT_LIVE_ENABLED", "1")
    output = tmp_path / "packet"
    manifest = generator.prepare(output)
    return output, manifest


def test_packet_preserves_committed_identity_and_separates_materials(packet):
    output, manifest = packet
    bundle_path = ROOT / "evidence/bundle.json"
    bundle = load_bundle(bundle_path)
    assert manifest["bundle_sha256"] == hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    assert manifest["recorded_source_digest"] == bundle.source_digest
    assert manifest["recorded_config_fingerprint"] == bundle.config_fingerprint
    assert manifest["recorded_git_commit"] == bundle.git_commit
    assert manifest["provider_requests"] == manifest["training_jobs"] == 0
    assert manifest["evidence_unchanged"]
    assert not manifest["engineer_study_conducted"] and not manifest["ai_outputs_included"]
    for name, fingerprint in manifest["files"].items():
        data = (output / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == fingerprint
        assert b"secret-test-marker-never-export" not in data
    reviewer = (output / "reviewer/manual.html").read_text(encoding="utf-8")
    assert "Deterministic analysis" not in reviewer and "Acceptable next-check criteria" not in reviewer
    assert "answer-key" not in reviewer
    assert 'src="http' not in reviewer and '<script' not in reviewer
    assert "no engineer sessions conducted" in reviewer
    local = (output / "reviewer/local.html").read_text(encoding="utf-8")
    assert Links(reviewer).hrefs == Links(local).hrefs == [f"evidence/C{id:02}.csv" for id in range(9, 13)]


def test_packet_keys_retain_decisive_facts_and_honest_unavailable_cases(packet):
    output, manifest = packet
    cases = json.loads((output / "facilitator/cases.json").read_text(encoding="utf-8"))
    answers = json.loads((output / "facilitator/answer-key.json").read_text(encoding="utf-8"))
    assert len(cases) == len(answers) == manifest["case_count"] == 12
    by_id = {case["id"]: case for case in cases}
    keyed = {answer["case_id"]: answer for answer in answers}
    for case in cases:
        result = case["result"]
        assert result["mode"] == "evidence" and result["model"] is None
        refs = {source["id"] for source in result["sources"]}
        assert all(set(claim["source_ids"]) <= refs for claim in result["assessment"])
        assert keyed[case["id"]]["evidence_digest"] == result["evidence_digest"]
        assert not keyed[case["id"]]["engineer_adjudicated"]
        assert all(source["partition"] == case["context"]["partition"] for source in result["sources"])
    failure = " ".join(claim["text"] for claim in by_id["C02"]["result"]["assessment"])
    assert "51.25%" in failure and "70%" in failure and "39 fewer timely warnings" in failure
    for fact in ["missing-reading flags", "median imputation", "late and missed warnings"]:
        assert fact in keyed["C02"]["acceptable_next_check"]
        assert by_id["C02"]["brief_example"]["text"].count(fact) == 1
    assert by_id["C02"]["brief_example"]["context"]["task"] == "brief"
    assert by_id["C07"]["raw"]["replay"]["selected_point"] is None
    assert "Abstain" in keyed["C07"]["acceptable_next_check"]
    assert by_id["C08"]["kind"] == "synthetic protocol fixture"
    alarm = " ".join(claim["text"] for claim in by_id["C08"]["result"]["assessment"])
    assert "15%" in alarm and "10%" in alarm
    assert keyed["C08"]["acceptable_next_check"] != keyed["C08"]["local_next_check"]
    assert "invent failure labels" in keyed["C10"]["essential_facts"][0]["text"]
    assert "training medians" in " ".join(claim["text"] for claim in keyed["C11"]["essential_facts"])
    assert "Duplicate equipment/cycle pairs" in keyed["C12"]["essential_facts"][0]["text"]
    for id in ["C09", "C10", "C11", "C12"]:
        path = output / "reviewer" / by_id[id]["raw"]["csv"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == by_id[id]["raw"]["file_sha256"]


def test_score_sheet_leaves_observations_blank_and_ai_unavailable(packet):
    output, _ = packet
    with (output / "score-sheet.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 36
    for row in rows:
        assert None not in row  # No row has surplus columns.
        assert row["status"] == ("not_available" if row["method"] == "ai" else "not_started")
        assert not any(row[column] for column in ["decision", "review_seconds", "next_check_quality_0_2",
                                                 "critical_misunderstandings", "helpfulness_1_5"])
    with (output / "method-order.csv").open(encoding="utf-8", newline="") as stream:
        order = list(csv.DictReader(stream))
    assert len(order) == 3
    for position in ["first_method", "second_method", "third_method"]:
        assert {row[position] for row in order} == {"manual", "local", "ai"}


def test_generator_is_repeatable_refuses_overwrite_and_leaves_original_untouched(generator, packet, tmp_path):
    output, manifest = packet
    original = (ROOT / "evidence/bundle.json").read_bytes()
    second = generator.prepare(tmp_path / "second")
    assert second == manifest
    assert (ROOT / "evidence/bundle.json").read_bytes() == original
    observations = output / "score-sheet.csv"
    observations.write_text("keep my observations", encoding="utf-8")
    with pytest.raises(ValueError, match="never overwritten"):
        generator.prepare(output)
    assert observations.read_text(encoding="utf-8") == "keep my observations"


def test_inadequate_bundle_is_rejected_before_output_and_html_escapes_text(generator, tmp_path):
    bundle = load_bundle(ROOT / "evidence/bundle.json")
    bundle.development_selection.ranked = [row for row in bundle.development_selection.ranked if row.qualifies][:1]
    path = tmp_path / "unsupported.json"
    path.write_text(bundle.model_dump_json(), encoding="utf-8")
    output = tmp_path / "not-created"
    with pytest.raises(ValueError, match="two passing models"):
        generator.prepare(output, path)
    assert not output.exists()
    assert "&lt;script&gt;" in generator._page("<script>", "")
    assert "&quot;" in generator._text('"quote"')


def test_alternate_bundle_selects_suitable_dropout_and_early_inactive_contexts(generator, tmp_path):
    bundle = load_bundle(ROOT / "evidence/bundle.json")
    # An alarm-only failing configuration comes last; it cannot be used with
    # the detection/dropout rubric. Replay storage order is not assumed.
    age = next(row for row in bundle.development_selection.ranked if row.config_id == "age1")
    age.qualifies = age.passes_clean = False
    age.clean.early_alarm_burden = 0.2
    bundle.development_selection.ranked.remove(age)
    bundle.development_selection.ranked.append(age)
    for series in bundle.replay_series:
        series.points.reverse()
    bundle.development_selection.criteria.max_early_alarm_burden = 0.95
    path = tmp_path / "alternative.json"
    path.write_text(bundle.model_dump_json(), encoding="utf-8")
    original = path.read_bytes()
    output = tmp_path / "alternate-packet"
    generator.prepare(output, path)
    assert path.read_bytes() == original
    cases = {case["id"]: case for case in json.loads((output / "facilitator/cases.json").read_text(encoding="utf-8"))}
    assert cases["C02"]["context"]["candidates"] == ["logistic_regression/lr2"]
    point = cases["C06"]["raw"]["replay"]["selected_point"]
    active = cases["C05"]["raw"]["replay"]["selected_point"]
    assert not point["alert"] and point["rul"] > bundle.development_selection.criteria.horizon_cycles
    assert point["cycle"] < active["cycle"]
    refs = {source["metric"]: source for source in cases["C08"]["result"]["sources"]}
    assert float(refs["clean_early_alarm_burden"]["value"]) == 1.0
    assert float(refs["max_early_alarm_burden"]["value"]) == 0.95


@pytest.mark.parametrize("problem,error", [
    ("alarm-only-failure", "decisive recorded fault is dropout"),
    ("no-early-inactive", "before its first active warning"),
    ("maximum-98", "at most 95%"),
    ("maximum-100", "at most 95%"),
])
def test_unsupported_valid_bundles_refuse_inaccurate_keys_without_writing(generator, tmp_path, problem, error):
    bundle = load_bundle(ROOT / "evidence/bundle.json")
    if problem == "alarm-only-failure":
        age = next(row for row in bundle.development_selection.ranked if row.config_id == "age1")
        age.qualifies = age.passes_clean = False
        age.clean.early_alarm_burden = 0.2
        bundle.development_selection.ranked = [row for row in bundle.development_selection.ranked if row.qualifies] + [age]
    elif problem == "no-early-inactive":
        for series in bundle.replay_series:
            series.points = [point for point in series.points if point.alert
                             or point.rul <= bundle.development_selection.criteria.horizon_cycles]
    else:
        bundle.development_selection.criteria.max_early_alarm_burden = 0.98 if problem == "maximum-98" else 1.0
    path = tmp_path / "unsupported-valid.json"
    path.write_text(bundle.model_dump_json(), encoding="utf-8")
    original = path.read_bytes()
    output = tmp_path / "not-created"
    with pytest.raises(ValueError, match=error):
        generator.prepare(output, path)
    assert path.read_bytes() == original
    assert not output.exists()
