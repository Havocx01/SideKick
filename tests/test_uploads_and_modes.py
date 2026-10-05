import io

import pytest
from app.config import reset_settings
from app.data.synthetic import make_synthetic_dataset
from fastapi.testclient import TestClient


@pytest.fixture
def csv_frame():
    dataset = make_synthetic_dataset(n_equipment=25, min_life=100, max_life=110)
    return dataset.frame[["equipment_id", "cycle", *dataset.sensors[:2], "failure_cycle"]].copy()


def confirm(client, frame, **changes):
    response = client.post("/api/datasets/upload", content=frame.to_csv(index=False), headers={"x-filename": "test.csv"})
    assert response.status_code == 200, response.text
    mapping = {"equipment_id": "equipment_id", "cycle_index": "cycle", "sensors": ["temp_bearing", "vibration_rms"], "failure_cycle": "failure_cycle"}
    mapping.update(changes.pop("mapping", {}))
    payload = {"mapping": mapping, "complete_histories": True, **changes}
    return client.post(f"/api/datasets/{response.json()['dataset_id']}/confirm", json=payload)


@pytest.mark.parametrize("issue", ["valid", "duplicate", "fractional", "conflicting", "overlap", "censored", "insufficient", "unconfirmed"])
def test_upload_contract(local_settings, csv_frame, issue):
    from app.main import create_app

    frame = csv_frame
    changes = {}
    if issue == "duplicate":
        import pandas as pd
        frame = pd.concat([frame, frame.iloc[:1]])
    elif issue == "fractional":
        frame["cycle"] = frame["cycle"].astype(float)
        frame.loc[0, "cycle"] = 1.5
    elif issue == "conflicting":
        frame.loc[0, "failure_cycle"] += 1
    elif issue == "overlap":
        changes["mapping"] = {"sensors": ["temp_bearing", "cycle"]}
    elif issue == "censored":
        frame["failure_cycle"] += 1
    elif issue == "insufficient":
        frame = frame[frame.equipment_id.isin(frame.equipment_id.unique()[:24])]
    elif issue == "unconfirmed":
        frame = frame.drop(columns="failure_cycle")
        changes = {"mapping": {"failure_cycle": None}, "complete_histories": False}
    with TestClient(create_app()) as client:
        response = confirm(client, frame, **changes)
        assert response.status_code == (200 if issue == "valid" else 422), response.text
        expected = {"duplicate": "Duplicate", "fractional": "whole numbers", "conflicting": "Conflicting",
            "overlap": "two roles", "censored": "Censored", "insufficient": "at least 25", "unconfirmed": "Confirm"}
        if issue != "valid":
            assert expected[issue] in response.json()["detail"]
        if issue == "valid":
            assert response.json()["confirmed"]
            assert len(response.json()["splits"]["holdout"]) == 20


def test_replay_mode_blocks_all_mutations(local_settings, monkeypatch):
    from app.main import create_app
    monkeypatch.setenv("SIDEKICK_MODE", "replay")
    reset_settings()
    with TestClient(create_app()) as client:
        id = "00000000-0000-0000-0000-000000000001"
        for path, payload in [("/api/datasets/sample", {}), ("/api/datasets/upload", {}),
            ("/api/experiments", {"dataset_id": id}), (f"/api/experiments/{id}/freeze", {}),
            (f"/api/experiments/{id}/validation", {"untouched_confirmed": True})]:
            assert client.post(path, json=payload).status_code == 403
        health = client.get("/api/health").json()
        assert not health["can_train"] and not health["can_freeze"]


def test_export_csv_matches_json(local_settings):
    import csv
    import json
    import zipfile

    from app.main import create_app

    with TestClient(create_app()) as client, zipfile.ZipFile(io.BytesIO(client.get("/api/export").content)) as archive:
        evidence = json.loads(archive.read("evidence.json"))
        rows = list(csv.DictReader(io.StringIO(archive.read("metrics.csv").decode())))
        indexed = {(r["candidate"], r["config_id"], r["scenario_id"], r["partition"]): r for r in evidence["scenario_results"]}
        assert len(rows) == len(indexed)
        for row in rows:
            source = indexed[(row["candidate"], row["config_id"], row["scenario_id"], row["partition"])]["metrics"]
            assert float(row["detection_fraction"]) == source["detection_fraction"]
            assert float(row["early_alarm_burden"]) == source["early_alarm_burden"]
