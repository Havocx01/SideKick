from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.experiments.store import Workspace


def seed(workspace, *, status="completed", source="upload"):
    dataset_id, run_id = str(uuid4()), str(uuid4())
    dataset = {"dataset_id": dataset_id, "name": "pump.csv", "source": source,
               "columns": ["cycle"], "preview": [], "row_count": 25, "confirmed": False}
    workspace.save_dataset(dataset)
    record = {"experiment_id": run_id, "dataset_id": dataset_id, "name": "pump.csv", "source": source,
              "status": status, "created_at": 100, "started_at": None, "finished_at": 120,
              "config": {}, "config_fingerprint": "fixed", "data_hash": "fixed", "source_digest": "fixed"}
    workspace.reserve(record)
    return dataset_id, run_id


def test_library_preserves_evidence_and_persists(tmp_path):
    from app.experiments.library import Library

    workspace = Workspace(tmp_path)
    upload, run = seed(workspace)
    original = workspace.get("experiments", run)
    library = Library(workspace)
    folder = library.create_folder("local", "  Pump A  ")
    library.change("local", [{"kind": "run", "id": run}], "rename", display_name="Baseline")
    library.change("local", [{"kind": "run", "id": run}, {"kind": "upload", "id": upload}], "move", folder_id=folder["id"])
    library.change("local", [{"kind": "run", "id": run}], "archive")
    reopened = Library(Workspace(tmp_path))
    items = {item["id"]: item for item in reopened.snapshot("local")["items"]}
    assert items[run]["archived"] and not items[upload]["archived"]
    assert items[run]["display_name"] == "Baseline"
    assert items[run]["folder_id"] == folder["id"]
    assert items[upload]["run_count"] == 1
    assert workspace.get("experiments", run) == original
    reopened.change("local", [{"kind": "run", "id": run}], "restore")
    reopened.remove_folder("local", folder["id"])
    assert all(item["folder_id"] is None for item in reopened.snapshot("local")["items"])
    assert workspace.get("experiments", run) == original


def test_bulk_archive_is_atomic_and_active_runs_are_protected(tmp_path):
    from app.experiments.library import Library

    workspace = Workspace(tmp_path)
    _, completed = seed(workspace)
    _, running = seed(workspace, status="running")
    library = Library(workspace)
    with pytest.raises(ValueError, match="running"):
        library.change("local", [{"kind": "run", "id": completed}, {"kind": "run", "id": running}], "archive")
    assert not any(item["archived"] for item in library.snapshot("local")["items"])
    with pytest.raises(KeyError):
        library.change("local", [{"kind": "run", "id": completed}, {"kind": "run", "id": str(uuid4())}], "archive")
    assert not any(item["archived"] for item in library.snapshot("local")["items"])


def test_legacy_dates_and_folder_inheritance(tmp_path):
    from app.experiments.library import Library

    workspace = Workspace(tmp_path)
    upload, _ = seed(workspace)
    # A record predating organization has no registration date to recover.
    with workspace.connect() as conn:
        conn.execute("DELETE FROM library_items WHERE id=?", (upload,))
    library = Library(workspace)
    assert next(item for item in library.snapshot("local")["items"] if item["id"] == upload)["created_at"] is None
    folder = library.create_folder("local", "Equipment")
    library.change("local", [{"kind": "upload", "id": upload}], "move", folder_id=folder["id"])
    library.change("local", [{"kind": "upload", "id": upload}], "archive")
    record = {**workspace.list()[0], "experiment_id": str(uuid4())}
    workspace.reserve(record, library_owner="local")
    item = next(item for item in library.snapshot("local")["items"] if item["id"] == record["experiment_id"])
    assert item["folder_id"] == folder["id"] and not item["archived"]
    explicit = {**record, "experiment_id": str(uuid4())}
    workspace.reserve(explicit, library_owner="local", folder_id=None, folder_explicit=True)
    assert next(item for item in library.snapshot("local")["items"] if item["id"] == explicit["experiment_id"])["folder_id"] is None


def test_api_library_guards_and_validation(local_settings):
    from app.main import create_app

    with TestClient(create_app()) as client:
        upload, run = seed(client.app.state.jobs.workspace)
        create = client.post("/api/library/folders", json={"name": "Pump A"})
        assert create.status_code == 201, create.text
        folder = create.json()
        assert client.post("/api/library/folders", json={"name": "pump a"}).status_code == 409
        for name in [" ", "x" * 81]:
            assert client.post("/api/library/folders", json={"name": name}).status_code == 422
        change = {"items": [{"kind": "run", "id": run}], "action": "rename", "display_name": "Baseline"}
        assert client.post("/api/library/items", json=change).status_code == 200
        assert client.post("/api/library/items", json={**change, "display_name": " "}).status_code == 422
        assert client.post("/api/library/items", json={**change, "display_name": "x" * 121}).status_code == 422
        assert client.post("/api/library/items", json=change, headers={"Origin": "https://invalid.example"}).status_code == 403
        assert client.post("/api/library/items", json={"items": [{"kind": "upload", "id": upload}], "action": "move", "folder_id": str(uuid4())}).status_code == 404
        assert client.post(f"/api/library/folders/{folder['id']}/rename", json={"name": "Compressor"}).status_code == 200
        assert client.post(f"/api/library/folders/{folder['id']}/remove").status_code == 200
        snapshot = client.get("/api/library").json()
        assert len(snapshot["items"]) == 2
        assert all("preview" not in item and "config" not in item for item in snapshot["items"])
        assert client.get(f"/api/experiments/{run}").json()["name"] == "pump.csv"
        assert client.post("/api/library/items", json={"items": [{"kind": "run", "id": run}], "action": "archive"}).status_code == 200
        assert any(record["experiment_id"] == run for record in client.get("/api/experiments").json())


def test_demo_organization_isolation(local_settings, monkeypatch):
    from app.config import reset_settings
    from app.main import create_app

    monkeypatch.setenv("SIDEKICK_MODE", "demo")
    reset_settings()
    with TestClient(create_app()) as first:
        upload, run = seed(first.app.state.jobs.workspace, source="synthetic")
        first.get("/api/health")
        from hashlib import sha256
        visitor = sha256(first.cookies["sidekick_demo"].encode()).hexdigest()
        first.app.state.demo.claim("datasets", upload, visitor)
        first.app.state.demo.claim("experiments", run, visitor)
        headers = {"X-Sidekick-Request": "1"}
        folder = first.post("/api/library/folders", json={"name": "Private"}, headers=headers).json()
        assert first.post("/api/library/items", json={"items": [{"kind": "run", "id": run}], "action": "move", "folder_id": folder["id"]}, headers=headers).status_code == 200
        first.cookies.clear()
        assert first.get("/api/library").json() == {"folders": [], "items": []}
        assert first.post("/api/library/items", json={"items": [{"kind": "run", "id": run}], "action": "archive"}, headers=headers).status_code == 404
        assert first.post(f"/api/library/folders/{folder['id']}/remove", headers=headers).status_code == 404


def test_upload_registration_folder_and_resumption(local_settings):
    from app.main import create_app

    application = create_app()
    with TestClient(application) as client:
        folder = client.post("/api/library/folders", json={"name": "Pump"}).json()
        csv = "equipment_id,cycle,temp,failure_cycle\nP1,1,2.5,2\nP1,2,3.5,2\n"
        uploaded = client.post("/api/datasets/upload", content=csv, headers={"X-Filename": "pump.csv", "X-Folder-Id": folder["id"]})
        assert uploaded.status_code == 200, uploaded.text
        upload_id = uploaded.json()["dataset_id"]
        item = client.get("/api/library").json()["items"][0]
        assert item["folder_id"] == folder["id"] and item["created_at"] is not None
        assert item["status"] == "needs_mapping"
        assert client.get(f"/api/datasets/{upload_id}").json() == uploaded.json()
        assert application.state.jobs.workspace.list() == []
        assert client.post("/api/datasets/upload", content=csv, headers={"X-Folder-Id": str(uuid4())}).status_code == 404
    with TestClient(application) as client:
        assert client.get("/api/library").json()["items"][0]["folder_id"] == folder["id"]
        assert client.get(f"/api/datasets/{upload_id}").json() == uploaded.json()


def test_new_runs_inherit_or_override_upload_folder_without_changing_config(local_settings, monkeypatch):
    from app.main import create_app
    from app.experiments.datasets import sample
    from app.experiments.jobs import Jobs

    # Exercise preparation and reservation, never execute a model-training worker.
    monkeypatch.setattr(Jobs, "_run", lambda self, id: None)
    with TestClient(create_app()) as client:
        workspace = client.app.state.jobs.workspace
        data = sample(workspace, hosted=True)
        folder = client.post("/api/library/folders", json={"name": "Source equipment"}).json()
        csv = (workspace.directory("datasets", data.dataset_id) / "data.csv").read_bytes()
        uploaded = client.post("/api/datasets/upload", content=csv, headers={"X-Folder-Id": folder["id"]}).json()
        assert client.post(f"/api/datasets/{uploaded['dataset_id']}/confirm", json={"mapping": data.mapping.model_dump(mode="json"), "complete_histories": True}).status_code == 200
        first = client.post("/api/experiments", json={"dataset_id": uploaded["dataset_id"]})
        assert first.status_code == 201, first.text
        inherited = first.json()
        workspace.update(inherited["experiment_id"], status="completed")
        second = client.post("/api/experiments", json={"dataset_id": uploaded["dataset_id"], "folder_id": None})
        assert second.status_code == 201, second.text
        override = second.json()
        items = {item["id"]: item for item in client.get("/api/library").json()["items"]}
        assert items[inherited["experiment_id"]]["folder_id"] == folder["id"]
        assert items[override["experiment_id"]]["folder_id"] is None
        assert inherited["config_fingerprint"] == override["config_fingerprint"]
        assert "folder_id" not in inherited["config"]


def test_demo_cleanup_removes_expired_organization(local_settings, monkeypatch):
    from app.config import reset_settings
    from app.main import create_app
    from app.experiments.library import Library

    monkeypatch.setenv("SIDEKICK_MODE", "demo")
    reset_settings()
    with TestClient(create_app()) as client:
        workspace = client.app.state.jobs.workspace
        upload, run = seed(workspace, source="synthetic")
        demo = client.app.state.demo
        demo.claim("datasets", upload, "visitor")
        demo.claim("experiments", run, "visitor")
        folder = Library(workspace).create_folder("demo:visitor", "Expired")
        Library(workspace).change("demo:visitor", [{"kind": "run", "id": run}], "move", folder_id=folder["id"])
        with workspace.connect() as conn:
            conn.execute("UPDATE demo_owners SET created=0")
            conn.execute("UPDATE library_folders SET created_at=0")
        demo.cleanup()
        assert Library(workspace).snapshot("demo:visitor") == {"folders": [], "items": []}
        with workspace.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM library_items").fetchone()[0] == 0


def test_replay_blocks_library(local_settings, monkeypatch):
    from app.config import reset_settings
    from app.main import create_app

    monkeypatch.setenv("SIDEKICK_MODE", "replay")
    reset_settings()
    with TestClient(create_app()) as client:
        assert client.get("/api/library").status_code == 403
        assert client.post("/api/library/folders", json={"name": "Folder"}).status_code == 403


def test_result_label_is_read_only_targeted_and_survives_archive(local_settings, monkeypatch):
    from app.experiments.library import Library
    from app.main import create_app

    with TestClient(create_app()) as client:
        workspace = client.app.state.jobs.workspace
        _, run = seed(workspace)
        original = workspace.get("experiments", run)
        assert client.get(f"/api/experiments/{run}").json()["display_name"] is None
        library = Library(workspace)
        library.change("local", [{"kind": "run", "id": run}], "rename", display_name="Pump commissioning")
        library.change("local", [{"kind": "run", "id": run}], "archive")
        # Detail must not scan the complete library for a single label.
        monkeypatch.setattr(Library, "snapshot", lambda *args: pytest.fail("Unexpected snapshot scan"))
        response = client.get(f"/api/experiments/{run}")
        assert response.status_code == 200
        assert response.json()["display_name"] == "Pump commissioning"
        assert response.json()["name"] == "pump.csv"
        assert workspace.get("experiments", run) == original
        assert "display_name" not in original
        assert client.get("/api/experiments").json()[0]["name"] == "pump.csv"


def test_result_display_name_never_crosses_demo_owners(local_settings, monkeypatch):
    from app.config import reset_settings
    from app.experiments.library import Library
    from app.main import create_app
    from hashlib import sha256

    monkeypatch.setenv("SIDEKICK_MODE", "demo")
    reset_settings()
    with TestClient(create_app()) as client:
        dataset, run = seed(client.app.state.jobs.workspace, source="synthetic")
        client.get("/api/health")
        visitor = sha256(client.cookies["sidekick_demo"].encode()).hexdigest()
        client.app.state.demo.claim("datasets", dataset, visitor)
        client.app.state.demo.claim("experiments", run, visitor)
        labels = Library(client.app.state.jobs.workspace)
        labels.change(f"demo:{visitor}", [{"kind": "run", "id": run}], "rename", display_name="Private label")
        labels.change("demo:another-visitor", [{"kind": "run", "id": run}], "rename", display_name="Wrong owner's label")
        assert client.get(f"/api/experiments/{run}").json()["display_name"] == "Private label"
        client.cookies.clear()
        assert client.get(f"/api/experiments/{run}").status_code == 404

def test_demo_folder_storage_caps_are_atomic_and_local_is_exempt(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from app.assistant.store import AnalysisCapacityError
    from app.experiments.library import Library
    library = Library(Workspace(tmp_path))
    def create(index):
        try:
            return library.create_folder(f'demo:{index}', f'Folder {index}', max_demo_folders=2, max_visitor_folders=1)
        except AnalysisCapacityError:
            return None
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert len([folder for folder in pool.map(create, range(6)) if folder]) == 2
    assert library.create_folder('local', 'Local unaffected')
    with library.workspace.connect() as db:
        owner, id = db.execute("SELECT owner,id FROM library_folders WHERE owner LIKE 'demo:%' LIMIT 1").fetchone()
    with pytest.raises(AnalysisCapacityError):
        library.create_folder(owner, 'Another', max_demo_folders=10, max_visitor_folders=1)
    library.rename_folder(owner, id, 'Retained folder')
    with library.workspace.connect() as db:
        db.execute('UPDATE library_folders SET created_at=0 WHERE id=?', (id,))
    assert create(7)
