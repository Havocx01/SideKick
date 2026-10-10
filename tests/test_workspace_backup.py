"""Recovery preserves evidence and privacy; it cannot overwrite a live workspace."""
import importlib.util
import json
import sqlite3
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest

from app.assistant.store import AssistantStore
from app.assistant.schemas import AnalysisRecord, AnalysisRequest
from app.experiments.jobs import Jobs
from app.experiments.store import Workspace


def module():
    spec = importlib.util.spec_from_file_location("workspace_backup", Path(__file__).resolve().parents[1] / "scripts/workspace_backup.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.fixture
def saved(tmp_path):
    data, artifacts = tmp_path / "data", tmp_path / "artifacts"
    data.mkdir()
    (data / "reference.csv").write_bytes(b"equipment,cycle,sensor\n001,1,0.2\n")
    workspace = Workspace(artifacts / "workspace")
    dataset_id, run_id, folder_id, analysis_id = (str(uuid4()) for _ in range(4))
    workspace.save_dataset({"dataset_id": dataset_id, "name": "original.csv", "confirmed": False,
                            "mapping": {"equipment_id": "equipment"}})
    dataset_dir = workspace.directory("datasets", dataset_id)
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "data.csv").write_bytes(b"equipment,cycle,sensor\n001,1,0.2\n")
    workspace.reserve({"experiment_id": run_id, "dataset_id": dataset_id, "status": "completed",
                       "name": "Original run", "created_at": 1, "started_at": None, "finished_at": 2, "elapsed_seconds": 0,
                       "data_hash": "recorded-fingerprint"})
    directory = workspace.directory("experiments", run_id)
    directory.mkdir(parents=True)
    (directory / "bundle.json").write_bytes(b'{"evidence":"immutable fixture"}')
    (directory / "model.joblib").write_bytes(b"frozen model fixture: do not deserialize")
    workspace.expose(["history-fingerprint"], run_id, "validation")
    workspace.save_pilot_part(run_id, "agreement", {"reviewer": "Fixture engineer"})
    with workspace.connect() as db:
        db.execute("INSERT INTO library_folders VALUES (?,?,?,?,?)", (folder_id, "local", "Pilot", "pilot", 1))
        db.execute("UPDATE library_items SET folder_id=?, display_name='Saved label', archived=1 WHERE kind='run'", (folder_id,))
    assistant = AssistantStore(artifacts / "assistant")
    record = AnalysisRecord(id=analysis_id, context=AnalysisRequest(task="investigate", candidates=["logistic_regression/lr2"]),
                            status="completed", created_at=1, updated_at=2, stages=[], brief_text="Edited brief")
    with assistant.connect() as db:
        db.execute("INSERT INTO analyses(id,owner,payload) VALUES (?,?,?)",
                   (analysis_id, "original-owner-hash", record.model_dump_json()))
        db.execute("INSERT INTO analysis_provenance VALUES (?,?,?,?)", (analysis_id, "cloud", "cloud", 1))
        db.execute("INSERT INTO consent VALUES (?,?,?)", ("original-owner-hash", run_id, 0))
    (artifacts / ".env").write_text("OPENAI_API_KEY=fixture-secret")
    (data / ".ENV").write_text("OPENAI_API_KEY=uppercase-fixture-secret")
    (data / ".Env.local").write_text("OPENAI_API_KEY=mixed-case-fixture-secret")
    (data / "private.key").write_text("fixture-secret")
    bundle = tmp_path / "bundle.json"
    bundle.write_bytes(b'{"benchmark":"recorded fixture"}')
    return data, artifacts, bundle, dataset_id, run_id, analysis_id


def test_roundtrip_preserves_ids_folders_evidence_mapping_briefs_and_privacy(saved, tmp_path):
    tool = module()
    data, artifacts, bundle, dataset_id, run_id, analysis_id = saved
    archive = tmp_path / "backup.zip"
    tool.create_backup(data, artifacts, bundle, archive)
    receipt = tool.inspect_backup(archive)
    assert receipt["format"] == "sidekick-workspace-backup" and receipt["version"] == 1
    restored = tmp_path / "restored"
    tool.restore_backup(archive, restored)
    workspace = Workspace(restored / "artifacts/workspace")
    assert workspace.get("datasets", dataset_id)["mapping"] == {"equipment_id": "equipment"}
    assert workspace.get("experiments", run_id)["data_hash"] == "recorded-fingerprint"
    assert workspace.exposed(["history-fingerprint"]) == ["history-fingerprint"]
    assert workspace.pilot(run_id)["agreement"]["reviewer"] == "Fixture engineer"
    assert (workspace.directory("experiments", run_id) / "bundle.json").read_bytes() == b'{"evidence":"immutable fixture"}'
    with workspace.connect() as db:
        assert db.execute("SELECT display_name,archived FROM library_items WHERE id=?", (run_id,)).fetchone() == ("Saved label", 1)
        assert db.execute("SELECT name FROM library_folders").fetchone() == ("Pilot",)
    with sqlite3.connect(restored / "artifacts/assistant/assistant.sqlite3") as db:
        owner, payload = db.execute("SELECT owner,payload FROM analyses WHERE id=?", (analysis_id,)).fetchone()
        assert owner == "original-owner-hash" and json.loads(payload)["brief_text"] == "Edited brief"
        assert db.execute("SELECT result_origin,brief_origin,revoked FROM analysis_provenance").fetchone() == ("cloud", "cloud", 1)
        assert db.execute("SELECT allowed FROM consent").fetchone() == (0,)
    assert (restored / "evidence/bundle.json").read_bytes() == bundle.read_bytes()
    # Open the restored stores like a server restart; migrations cannot declassify origin/revocation.
    jobs = Jobs(restored / "artifacts/workspace")
    try:
        assert jobs.workspace.get("experiments", run_id)["status"] == "completed"
        assert jobs.workspace.exposed(["history-fingerprint"]) == ["history-fingerprint"]
    finally:
        jobs.close()
    assistant = AssistantStore(restored / "artifacts/assistant")
    with pytest.raises(KeyError):
        assistant.get(analysis_id, "another-owner")
    with assistant.connect() as db:
        assert db.execute("SELECT brief_origin,revoked FROM analysis_provenance").fetchone() == ("cloud", 1)
    with zipfile.ZipFile(archive) as z:
        assert not any(".env" in name.casefold() or "private.key" in name or name.endswith("server.lock") for name in z.namelist())


def test_rejects_running_server_and_active_jobs(saved, tmp_path):
    tool = module()
    data, artifacts, bundle, _, run_id, _ = saved
    jobs = Jobs(artifacts / "workspace")
    try:
        with pytest.raises(tool.BackupError, match="Stop"):
            tool.create_backup(data, artifacts, bundle, tmp_path / "live.zip")
    finally:
        jobs.close()
    with sqlite3.connect(artifacts / "workspace/workspace.sqlite3") as db:
        db.execute("UPDATE experiments SET status='running' WHERE id=?", (run_id,))
    with pytest.raises(tool.BackupError, match="active"):
        tool.create_backup(data, artifacts, bundle, tmp_path / "active.zip")
    assert not (tmp_path / "active.zip").exists()


def test_rejects_active_analysis(saved, tmp_path):
    tool = module()
    data, artifacts, bundle, *_ = saved
    with sqlite3.connect(artifacts / "assistant/assistant.sqlite3") as db:
        db.execute("UPDATE analyses SET payload=?", (json.dumps({"status": "running"}),))
    with pytest.raises(tool.BackupError, match="analysis"):
        tool.create_backup(data, artifacts, bundle, tmp_path / "active.zip")


def test_never_overwrites_archive_or_destination(saved, tmp_path):
    tool = module()
    data, artifacts, bundle, *_ = saved
    archive = tmp_path / "backup.zip"
    archive.write_bytes(b"existing")
    with pytest.raises(tool.BackupError, match="exists"):
        tool.create_backup(data, artifacts, bundle, archive)
    assert archive.read_bytes() == b"existing"
    archive.unlink()
    tool.create_backup(data, artifacts, bundle, archive)
    dest = tmp_path / "existing"
    dest.mkdir()
    (dest / "keep.txt").write_text("untouched")
    with pytest.raises(tool.BackupError, match="exists"):
        tool.restore_backup(archive, dest)
    assert (dest / "keep.txt").read_text() == "untouched"


@pytest.mark.parametrize("bad_name", [".", "../outside", "artifacts/../../outside", "C:/outside", "artifacts\\outside", "artifacts/file:stream",
                                     "data/.ENV", "artifacts/.Env.local"])
def test_unsafe_archive_names_leave_no_destination(tmp_path, bad_name):
    tool = module()
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(bad_name, b"unsafe")
        z.writestr("backup-manifest.json", '{}')
    with pytest.raises(tool.BackupError):
        tool.restore_backup(archive, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()
    assert not (tmp_path / "outside").exists()


def test_zip_symlink_rejected_without_os_link_permissions(tmp_path):
    tool = module()
    archive = tmp_path / "linked.zip"
    entry = zipfile.ZipInfo("artifacts/link")
    entry.create_system = 3
    entry.external_attr = 0o120777 << 16
    with zipfile.ZipFile(archive, "w") as dest:
        dest.writestr(entry, b"../../outside")
        dest.writestr("backup-manifest.json", '{}')
    with pytest.raises(tool.BackupError, match="links"):
        tool.restore_backup(archive, tmp_path / "linked-restore")
    assert not (tmp_path / "linked-restore").exists()


def test_corruption_missing_files_and_duplicates_rejected(saved, tmp_path):
    tool = module()
    data, artifacts, bundle, *_ = saved
    original = tmp_path / "backup.zip"
    tool.create_backup(data, artifacts, bundle, original)
    for mode in ("changed", "missing", "duplicate"):
        bad = tmp_path / f"{mode}.zip"
        with zipfile.ZipFile(original) as src, zipfile.ZipFile(bad, "w") as dest:
            for entry in src.infolist():
                if entry.filename == "data/reference.csv":
                    if mode == "missing":
                        continue
                    if mode == "changed":
                        dest.writestr(entry, b"changed")
                        continue
                dest.writestr(entry, src.read(entry))
            if mode == "duplicate":
                with pytest.warns(UserWarning):
                    dest.writestr("data/reference.csv", b"duplicate")
        with pytest.raises(tool.BackupError):
            tool.restore_backup(bad, tmp_path / f"restore-{mode}")
        assert not (tmp_path / f"restore-{mode}").exists()


def test_sqlite_wal_committed_records_are_included(saved, tmp_path):
    tool = module()
    data, artifacts, bundle, *_ = saved
    with sqlite3.connect(artifacts / "workspace/workspace.sqlite3") as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("INSERT INTO exposures VALUES ('wal-history','fixture','development',1)")
        db.commit()
        archive = tmp_path / "wal.zip"
        tool.create_backup(data, artifacts, bundle, archive)
    tool.restore_backup(archive, tmp_path / "wal-restore")
    with sqlite3.connect(tmp_path / "wal-restore/artifacts/workspace/workspace.sqlite3") as db:
        assert db.execute("SELECT reason FROM exposures WHERE history_id='wal-history'").fetchone() == ("development",)


def test_source_change_during_copy_fails_without_publishing(saved, tmp_path, monkeypatch):
    tool = module()
    data, artifacts, bundle, *_ = saved
    original = tool.write_file
    changed = False

    def mutate(archive, path, name):
        nonlocal changed
        entry = original(archive, path, name)
        if not changed and name == "data/reference.csv":
            changed = True
            path.write_bytes(b"changed after snapshot")
        return entry

    monkeypatch.setattr(tool, "write_file", mutate)
    with pytest.raises(tool.BackupError, match="changed"):
        tool.create_backup(data, artifacts, bundle, tmp_path / "changed.zip")
    assert not (tmp_path / "changed.zip").exists()


def test_rejects_source_symlink(saved, tmp_path):
    tool = module()
    data, artifacts, bundle, *_ = saved
    link = data / "link.csv"
    try:
        link.symlink_to(bundle)
    except OSError:
        pytest.skip("Creating symlinks requires platform permission")
    with pytest.raises(tool.BackupError, match="link"):
        tool.create_backup(data, artifacts, bundle, tmp_path / "linked.zip")


def test_cli_honors_configured_paths_without_copying_credentials(saved, tmp_path, monkeypatch, capsys):
    import dotenv
    tool = module()
    data, artifacts, bundle, *_ = saved
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: None)
    for name, value in (("SIDEKICK_DATA_DIR", data), ("SIDEKICK_ARTIFACTS_DIR", artifacts), ("SIDEKICK_BUNDLE_PATH", bundle)):
        monkeypatch.setenv(name, str(value))
    monkeypatch.setenv("SIDEKICK_MODE", "full")
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-secret-that-must-not-appear")
    archive = tmp_path / "configured.zip"
    assert tool.main(["create", "--output", str(archive)]) == 0
    assert tool.main(["verify", str(archive)]) == 0
    assert tool.main(["restore", str(archive), "--destination", str(tmp_path / "configured-restore")]) == 0
    assert "fixture-secret" not in capsys.readouterr().out
    monkeypatch.setenv("SIDEKICK_MODE", "demo")
    assert tool.main(["create", "--output", str(tmp_path / "public.zip")]) == 1
    assert not (tmp_path / "public.zip").exists()


def test_invalid_database_is_rejected_before_restored_workspace_exists(saved, tmp_path):
    tool = module()
    data, artifacts, bundle, *_ = saved
    archive = tmp_path / "backup.zip"
    tool.create_backup(data, artifacts, bundle, archive)
    invalid = tmp_path / "invalid-database.zip"
    with zipfile.ZipFile(archive) as src:
        manifest = json.loads(src.read("backup-manifest.json"))
        replacement = b"not a SQLite database"
        import hashlib
        for entry in manifest["files"]:
            if entry["path"] == "artifacts/workspace/workspace.sqlite3":
                manifest["total_bytes"] += len(replacement) - entry["bytes"]
                entry.update(bytes=len(replacement), sha256=hashlib.sha256(replacement).hexdigest())
        with zipfile.ZipFile(invalid, "w") as dest:
            for entry in src.infolist():
                content = (json.dumps(manifest).encode() if entry.filename == "backup-manifest.json" else
                           replacement if entry.filename == "artifacts/workspace/workspace.sqlite3" else src.read(entry))
                dest.writestr(entry, content)
    with pytest.raises(tool.BackupError, match="database"):
        tool.restore_backup(invalid, tmp_path / "invalid-restore")
    assert not (tmp_path / "invalid-restore").exists()


def test_failed_publication_cleans_only_its_new_backup(saved, tmp_path, monkeypatch):
    tool = module()
    data, artifacts, bundle, *_ = saved
    existing = tmp_path / "existing.txt"
    existing.write_text("keep")

    def fail(*args, **kwargs):
        raise OSError("fixture disk full")

    monkeypatch.setattr(tool.shutil, "copyfileobj", fail)
    with pytest.raises(OSError):
        tool.create_backup(data, artifacts, bundle, tmp_path / "failed.zip")
    assert not (tmp_path / "failed.zip").exists()
    assert existing.read_text() == "keep"
    assert (data / "reference.csv").read_bytes().startswith(b"equipment")


def test_failed_restore_cleans_partial_new_workspace_only(saved, tmp_path, monkeypatch):
    tool = module()
    data, artifacts, bundle, *_ = saved
    archive = tmp_path / "backup.zip"
    tool.create_backup(data, artifacts, bundle, archive)
    original = tool.shutil.copytree

    def fail(source, target, *args, **kwargs):
        original(source, target, *args, **kwargs)
        raise OSError("fixture disk full during recovery")

    monkeypatch.setattr(tool.shutil, "copytree", fail)
    with pytest.raises(OSError):
        tool.restore_backup(archive, tmp_path / "partial")
    assert not (tmp_path / "partial").exists()
    assert (data / "reference.csv").read_bytes().startswith(b"equipment")
    assert archive.is_file()


def test_restored_public_records_keep_original_expiry(saved, tmp_path):
    tool = module()
    data, artifacts, bundle, _, _, analysis_id = saved
    with sqlite3.connect(artifacts / "assistant/assistant.sqlite3") as db:
        db.execute("UPDATE analyses SET public=1 WHERE id=?", (analysis_id,))
    archive = tmp_path / "historical.zip"
    tool.create_backup(data, artifacts, bundle, archive)
    tool.restore_backup(archive, tmp_path / "historical-restore")
    assistant = AssistantStore(tmp_path / "historical-restore/artifacts/assistant")
    assert assistant.expired(analysis_id, "original-owner-hash")
    with assistant.connect() as db:
        assert json.loads(db.execute("SELECT payload FROM analyses WHERE id=?", (analysis_id,)).fetchone()[0])["created_at"] == 1
