"""Offline local snapshots and no-overwrite recovery. Never deserializes model files."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import zipfile
from contextlib import ExitStack, closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "backup-manifest.json"
FORMAT = "sidekick-workspace-backup"
MAX_FILES = 200_000
MAX_BYTES = 100 * 1024**3
MAX_MANIFEST_BYTES = 32 * 1024**2
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache"}
SKIP_NAMES = {".gitkeep", "server.lock", ".ds_store", "thumbs.db"}
SECRET_SUFFIXES = {".key", ".pem", ".p12", ".pfx"}


class BackupError(ValueError):
    """Safe, user-facing failure without credentials or database contents."""


def excluded(path: PurePosixPath) -> bool:
    name = path.name.casefold()
    return (any(p.casefold() in SKIP_DIRS for p in path.parts)
            or name in SKIP_NAMES
            or name.startswith(".env") or path.suffix.lower() in SECRET_SUFFIXES
            or name.endswith(("-wal", "-shm", "-journal", ".log")))


def digest_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_name(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    windows_reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
    if (not name or not path.parts or "\\" in name or ":" in name or path.is_absolute()
            or name != path.as_posix() or any(part in {".", ".."} for part in path.parts)
            or any(part.rstrip(" .") != part or part.split(".")[0].lower() in windows_reserved for part in path.parts)
            or any(ord(char) < 32 for char in name)):
        raise BackupError("Backup contains an unsafe file name.")
    if name != MANIFEST and (name != "evidence/bundle.json" and (path.parts[0] not in {"data", "artifacts"} or len(path.parts) < 2)):
        raise BackupError("Backup contains a file outside its workspace roots.")
    if name != MANIFEST and excluded(path):
        raise BackupError("Backup contains excluded credentials or transient files.")
    return path


def inventory(data_dir: Path, artifacts_dir: Path, bundle_path: Path) -> dict[str, Path]:
    files = {}
    for label, root in (("data", data_dir), ("artifacts", artifacts_dir)):
        if not root.is_dir():
            raise BackupError(f"The configured {label} directory is unavailable.")
        for directory, folders, names in os.walk(root, followlinks=False):
            for name in folders[:]:
                path = Path(directory) / name
                if name.casefold() in SKIP_DIRS:
                    folders.remove(name)
                elif path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                    raise BackupError("Workspace links are unsupported; use real workspace directories.")
            for name in names:
                path = Path(directory) / name
                relative = PurePosixPath(label, path.relative_to(root).as_posix())
                if excluded(relative):
                    continue
                if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
                    raise BackupError("Workspace links or special files cannot be backed up.")
                safe_name(relative.as_posix())
                files[relative.as_posix()] = path
    if not bundle_path.is_file() or bundle_path.is_symlink():
        raise BackupError("The configured recorded evidence bundle is unavailable.")
    files["evidence/bundle.json"] = bundle_path
    if len(files) > MAX_FILES or sum(path.stat().st_size for path in files.values()) > MAX_BYTES:
        raise BackupError("Workspace exceeds this tool's 200,000-file / 100 GiB safety limit.")
    return dict(sorted(files.items()))


@contextmanager
def stopped_workspace(artifacts_dir: Path):
    # Share the exact OS lock used by Jobs. Holding it prevents a full-mode server start.
    directory = artifacts_dir / "workspace"
    if directory.is_symlink() or (hasattr(directory, "is_junction") and directory.is_junction()):
        raise BackupError("Workspace links are unsupported.")
    directory.mkdir(exist_ok=True)
    lock_path = directory / "server.lock"
    if lock_path.is_symlink():
        raise BackupError("Workspace lock cannot be a link.")
    with lock_path.open("a+b") as stream:
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise BackupError("Stop the Sidekick server before backing up. No files were copied.") from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def connect_existing(path: Path):
    return sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=1)


def check_database(db: sqlite3.Connection):
    if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
        raise BackupError("A workspace database failed its integrity check.")
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "experiments" in tables:
        if db.execute("SELECT 1 FROM experiments WHERE status IN ('queued','running','cancelling') LIMIT 1").fetchone():
            raise BackupError("An active experiment remains. Stop or recover it before backing up.")
    if "analyses" in tables:
        for (payload,) in db.execute("SELECT payload FROM analyses"):
            try:
                status = json.loads(payload).get("status")
            except (ValueError, AttributeError):
                continue  # Preserve readable/unrecognised legacy records without rewriting them.
            if status in ("queued", "running"):
                raise BackupError("An active analysis remains. Stop or recover it before backing up.")


def write_file(archive: zipfile.ZipFile, path: Path, name: str) -> dict:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source, archive.open(name, "w", force_zip64=True) as target:
        while block := source.read(1024 * 1024):
            digest.update(block)
            size += len(block)
            if size > MAX_BYTES:
                raise BackupError("Workspace changed or exceeds the backup size limit.")
            target.write(block)
    return {"path": name, "bytes": size, "sha256": digest.hexdigest()}


def runtime_receipt() -> dict:
    versions = {}
    for name in ("numpy", "pandas", "scikit-learn", "xgboost", "joblib"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    return {"python": sys.version.split()[0], "packages": versions, "git_commit": commit}


def create_backup(data_dir: Path, artifacts_dir: Path, bundle_path: Path, archive_path: Path) -> dict:
    if Path(archive_path).expanduser().is_symlink():
        raise BackupError("Backup destination cannot be a link.")
    data_dir, artifacts_dir, bundle_path, archive_path = [Path(p).expanduser().resolve() for p in (data_dir, artifacts_dir, bundle_path, archive_path)]
    if data_dir.is_relative_to(artifacts_dir) or artifacts_dir.is_relative_to(data_dir):
        raise BackupError("Data and artifacts must be separate directories for a portable backup.")
    if archive_path.is_relative_to(data_dir) or archive_path.is_relative_to(artifacts_dir) or archive_path == bundle_path:
        raise BackupError("Save the backup outside its source directories.")
    if archive_path.exists():
        raise BackupError("Backup destination already exists. Choose a new file name.")
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with stopped_workspace(artifacts_dir), ExitStack() as locks, tempfile.TemporaryDirectory(prefix=".sidekick-backup-", dir=archive_path.parent) as temporary:
        paths = inventory(data_dir, artifacts_dir, bundle_path)
        snapshots = {}
        for name, path in paths.items():
            with path.open("rb") as stream:
                sqlite_header = stream.read(16) == b"SQLite format 3\x00"
            if not sqlite_header and path.suffix == ".sqlite3":
                raise BackupError("A workspace database is unreadable.")
            if sqlite_header:
                # Freeze writers across all databases, then use SQLite's backup API (includes WAL).
                guard = locks.enter_context(closing(connect_existing(path)))
                guard.execute("BEGIN IMMEDIATE")
                check_database(guard)
                snapshot = Path(temporary) / f"database-{len(snapshots)}.sqlite3"
                with closing(connect_existing(path)) as source, closing(sqlite3.connect(snapshot)) as target:
                    with target:
                        source.backup(target)
                snapshots[name] = snapshot
        temporary_zip = Path(temporary) / "backup.zip"
        entries = []
        with zipfile.ZipFile(temporary_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
            for name, path in paths.items():
                entries.append(write_file(archive, snapshots.get(name, path), name))
            if sum(entry["bytes"] for entry in entries) > MAX_BYTES:
                raise BackupError("Workspace exceeds the backup size limit.")
            current = inventory(data_dir, artifacts_dir, bundle_path)
            if paths != current or any(digest_file(paths[entry["path"]]) != entry["sha256"] for entry in entries if entry["path"] not in snapshots):
                raise BackupError("Workspace files changed during the backup. Stop all writers and retry.")
            manifest = {"format": FORMAT, "version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                        "runtime": runtime_receipt(), "files": entries, "total_bytes": sum(entry["bytes"] for entry in entries)}
            archive.writestr(MANIFEST, json.dumps(manifest, indent=2))
        inspect_backup(temporary_zip)
        # Exclusive creation prevents replacing an existing archive, including concurrent saves.
        try:
            with archive_path.open("xb") as target, temporary_zip.open("rb") as source:
                shutil.copyfileobj(source, target)
        except FileExistsError:
            raise BackupError("Backup destination already exists. Choose a new file name.") from None
        except BaseException:
            archive_path.unlink(missing_ok=True)
            raise
        return manifest


def validate_archive(archive: zipfile.ZipFile) -> dict:
    infos = archive.infolist()
    if len(infos) > MAX_FILES + 1 or sum(entry.file_size for entry in infos) > MAX_BYTES + MAX_MANIFEST_BYTES:
        raise BackupError("Backup exceeds the file count or expanded size safety limit.")
    names = {}
    for entry in infos:
        safe_name(entry.filename)
        if entry.is_dir() or stat.S_IFMT(entry.external_attr >> 16) not in (0, stat.S_IFREG):
            raise BackupError("Backup contains links or special entries.")
        key = entry.filename.casefold()
        if key in names:
            raise BackupError("Backup contains duplicate or conflicting file names.")
        names[key] = entry.filename
    if MANIFEST not in archive.namelist() or archive.getinfo(MANIFEST).file_size > MAX_MANIFEST_BYTES:
        raise BackupError("Backup manifest is missing or too large.")
    try:
        manifest = json.loads(archive.read(MANIFEST))
        if not isinstance(manifest, dict) or manifest.get("format") != FORMAT or manifest.get("version") != 1:
            raise BackupError("This is not a supported Sidekick workspace backup.")
        if type(manifest["version"]) is not int or not isinstance(manifest.get("created_at"), str):
            raise BackupError("Backup manifest is missing its format or date.")
        datetime.fromisoformat(manifest["created_at"])
        entries = manifest["files"]
        if not isinstance(entries, list) or len(entries) > MAX_FILES:
            raise BackupError("Backup manifest has invalid file records.")
        expected = set()
        total = 0
        for entry in entries:
            name = entry["path"]
            safe_name(name)
            if name == MANIFEST or name in expected or type(entry["bytes"]) is not int or entry["bytes"] < 0 or not re.fullmatch(r"[a-f0-9]{64}", entry["sha256"]):
                raise BackupError("Backup manifest has invalid file records.")
            expected.add(name)
            total += entry["bytes"]
            if archive.getinfo(name).file_size != entry["bytes"]:
                raise BackupError("Backup file sizes do not match the manifest.")
            with archive.open(name) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != entry["sha256"]:
                    raise BackupError("Backup checksum verification failed.")
        if set(archive.namelist()) != expected | {MANIFEST} or "evidence/bundle.json" not in expected or manifest["total_bytes"] != total or total > MAX_BYTES:
            raise BackupError("Backup is incomplete or contains unexpected files.")
        # Detect paths that would be both a file and a containing directory.
        for name in expected:
            if any(parent.as_posix().casefold() in names for parent in PurePosixPath(name).parents if parent != PurePosixPath(".")):
                raise BackupError("Backup has conflicting file and directory paths.")
        return manifest
    except (KeyError, TypeError, ValueError, UnicodeError) as exc:
        if isinstance(exc, BackupError):
            raise
        raise BackupError("Backup manifest or file records are invalid.") from None


def inspect_backup(archive_path: Path) -> dict:
    try:
        with zipfile.ZipFile(Path(archive_path).expanduser().resolve()) as archive:
            return validate_archive(archive)
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        raise BackupError("Backup archive is damaged or uses unsupported compression.") from exc


def restore_backup(archive_path: Path, destination: Path) -> dict:
    archive_path, destination = Path(archive_path).expanduser().resolve(), Path(destination).expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise BackupError("Restore destination already exists. Choose a new workspace directory.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination = destination.parent.resolve() / destination.name
    with tempfile.TemporaryDirectory(prefix=".sidekick-restore-", dir=destination.parent) as temporary:
        staging = Path(temporary)
        try:
            with zipfile.ZipFile(archive_path) as archive:
                manifest = validate_archive(archive)
                for entry in manifest["files"]:
                    path = staging.joinpath(*safe_name(entry["path"]).parts)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(entry["path"]) as source, path.open("xb") as target:
                        shutil.copyfileobj(source, target)
                    if digest_file(path) != entry["sha256"]:
                        raise BackupError("Backup changed during recovery.")
                    with path.open("rb") as stream:
                        is_database = stream.read(16) == b"SQLite format 3\x00"
                    if is_database:
                        with closing(connect_existing(path)) as db:
                            check_database(db)
                    elif path.suffix == ".sqlite3":
                        raise BackupError("Restored database is unreadable.")
                (staging / "data").mkdir(exist_ok=True)
                (staging / "artifacts").mkdir(exist_ok=True)
                (staging / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError):
            raise BackupError("Backup archive is damaged or uses unsupported compression.") from None
        try:
            destination.mkdir()  # Exclusive reservation; existing workspaces are never merged.
        except FileExistsError:
            raise BackupError("Restore destination already exists. Choose a new workspace directory.") from None
        try:
            for path in staging.iterdir():
                # Directory renames can be denied by Windows cloud-sync handles.
                # Copy into our exclusively reserved directory; failure removes only it.
                target = destination / path.name
                if path.is_dir():
                    shutil.copytree(path, target)
                else:
                    shutil.copyfile(path, target)
            if any(digest_file(destination / entry["path"]) != entry["sha256"] for entry in manifest["files"]):
                raise BackupError("Restored file checksum verification failed.")
        except BaseException:
            # Only this newly created directory is ours; never recurse over an existing workspace.
            if destination.parent == staging.parent and destination.resolve() == destination:
                shutil.rmtree(destination)
            raise
        return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Stop Sidekick, back up its local workspace, or restore into a new directory.")
    sub = parser.add_subparsers(dest="command", required=True)
    backup = sub.add_parser("create", help="Back up configured local data, artifacts and evidence")
    backup.add_argument("--output", type=Path)
    backup.add_argument("--data-dir", type=Path)
    backup.add_argument("--artifacts-dir", type=Path)
    backup.add_argument("--bundle", type=Path)
    verify = sub.add_parser("verify", help="Check every file checksum")
    verify.add_argument("archive", type=Path)
    restore = sub.add_parser("restore", help="Restore a trusted backup into a new workspace")
    restore.add_argument("archive", type=Path)
    restore.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            from dotenv import load_dotenv
            load_dotenv(ROOT / ".env", override=False)
            if os.environ.get("SIDEKICK_MODE", "full") != "full":
                raise BackupError("Workspace backup supports local full mode. Public demo/replay data retains its existing expiry policy.")
            def configured(value, env, fallback):
                raw = os.environ.get(env)
                return value or (Path(raw) if raw else fallback)
            output = args.output or ROOT / "output/backups" / f"sidekick-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.zip"
            receipt = create_backup(configured(args.data_dir, "SIDEKICK_DATA_DIR", ROOT / "data"),
                                    configured(args.artifacts_dir, "SIDEKICK_ARTIFACTS_DIR", ROOT / "artifacts"),
                                    configured(args.bundle, "SIDEKICK_BUNDLE_PATH", ROOT / "evidence/bundle.json"), output)
            print(f"Backup verified: {output.expanduser().resolve()}")
        elif args.command == "verify":
            receipt = inspect_backup(args.archive)
            print("Every backup file passed checksum verification.")
        else:
            receipt = restore_backup(args.archive, args.destination)
            print(f"Restored into new workspace: {args.destination.expanduser().resolve()}")
            print("Original workspace retained. See docs/workspace-backup.md for startup settings and ownership limitations.")
        print(f"{len(receipt['files'])} files; {receipt['total_bytes']:,} expanded bytes; saved {receipt['created_at']}")
        return 0
    except (BackupError, OSError, sqlite3.Error) as exc:
        message = str(exc) if isinstance(exc, BackupError) else "File or database access failed. Check paths, permissions, free space and that Sidekick is stopped."
        print(f"Backup/recovery failed: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
