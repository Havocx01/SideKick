"""Organization metadata, deliberately separate from immutable test evidence."""

import json
import sqlite3
import time
from uuid import uuid4

from app.experiments.store import ACTIVE, identifier


def validate_folder(conn, owner, folder_id):
    if folder_id is None:
        return
    identifier(folder_id)
    if not conn.execute("SELECT 1 FROM library_folders WHERE id=? AND owner=?", (folder_id, owner)).fetchone():
        raise KeyError(folder_id)


def clean_name(name, limit):
    name = name.strip()
    if not name or len(name) > limit:
        raise ValueError(f"Use a name between 1 and {limit} characters.")
    return name


class Library:
    def __init__(self, workspace):
        self.workspace = workspace

    def display_name(self, owner, run_id):
        """Read one owner's label without loading the library or mutating evidence."""
        with self.workspace.connect() as conn:
            row = conn.execute(
                "SELECT display_name FROM library_items WHERE owner=? AND kind='run' AND id=?",
                (owner, run_id),
            ).fetchone()
        return row[0] if row else None

    def snapshot(self, owner, allowed=None):
        with self.workspace.connect() as conn:
            folders = [dict(id=row[0], name=row[1]) for row in conn.execute(
                "SELECT id,name FROM library_folders WHERE owner=? ORDER BY name_key", (owner,))]
            folder_ids = {folder["id"] for folder in folders}
            metadata = {(row[0], row[1]): row[2:] for row in conn.execute(
                "SELECT kind,id,display_name,folder_id,archived,created_at FROM library_items WHERE owner=?", (owner,))}
            runs = [json.loads(row[0]) for row in conn.execute("SELECT payload FROM experiments")]
            datasets = [json.loads(row[0]) for row in conn.execute("SELECT payload FROM datasets")]
        runs = [run for run in runs if run.get("job_kind", "development") == "development"
                and (allowed is None or run["experiment_id"] in allowed["run"])]
        counts = {}
        for run in runs:
            counts[run["dataset_id"]] = counts.get(run["dataset_id"], 0) + 1
        items = []
        for kind, records in [("run", runs), ("upload", datasets)]:
            for record in records:
                id = record["experiment_id"] if kind == "run" else record["dataset_id"]
                if kind == "upload" and (record["source"] != "upload" or (allowed is not None and id not in allowed["upload"])):
                    continue
                name, folder, archived, registered = metadata.get((kind, id), (None, None, False, None))
                items.append({"kind": kind, "id": id, "dataset_id": record["dataset_id"],
                              "display_name": name or record["name"], "original_name": record["name"],
                              "source": record["source"], "folder_id": folder if folder in folder_ids else None,
                              "archived": bool(archived),
                              "created_at": record["created_at"] if kind == "run" else registered,
                              "status": record["status"] if kind == "run" else ("ready_to_train" if record["confirmed"] else "needs_mapping"),
                              "run_count": counts.get(record["dataset_id"], 0),
                              "row_count": record.get("row_count") if kind == "upload" else None})
        return {"folders": folders, "items": items}

    def create_folder(self, owner, name, *, max_demo_folders=2000, max_visitor_folders=100):
        name = clean_name(name, 80)
        folder = {"id": str(uuid4()), "name": name}
        try:
            with self.workspace.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                if owner.startswith("demo:"):
                    cutoff = time.time() - 86400
                    conn.execute("UPDATE library_items SET folder_id=NULL WHERE folder_id IN (SELECT id FROM library_folders WHERE owner LIKE 'demo:%' AND created_at < ?)", (cutoff,))
                    conn.execute("DELETE FROM library_folders WHERE owner LIKE 'demo:%' AND created_at < ?", (cutoff,))
                    total, personal = conn.execute("SELECT COUNT(*),COALESCE(SUM(owner=?),0) FROM library_folders WHERE owner LIKE 'demo:%'", (owner,)).fetchone()
                    if total >= max_demo_folders or personal >= max_visitor_folders:
                        from app.assistant.store import AnalysisCapacityError
                        raise AnalysisCapacityError("The shared demo is temporarily at folder storage capacity. Existing folders and items remain available.")
                conn.execute("INSERT INTO library_folders VALUES (?,?,?,?,?)",
                             (folder["id"], owner, name, name.casefold(), time.time()))
        except sqlite3.IntegrityError:
            raise ValueError("A folder with this name already exists. Choose another name.") from None
        return folder

    def rename_folder(self, owner, id, name):
        name = clean_name(name, 80)
        try:
            with self.workspace.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                validate_folder(conn, owner, id)
                conn.execute("UPDATE library_folders SET name=?,name_key=? WHERE id=? AND owner=?",
                             (name, name.casefold(), id, owner))
        except sqlite3.IntegrityError:
            raise ValueError("A folder with this name already exists. Choose another name.") from None
        return {"id": id, "name": name}

    def remove_folder(self, owner, id):
        with self.workspace.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            validate_folder(conn, owner, id)
            conn.execute("UPDATE library_items SET folder_id=NULL WHERE folder_id=? AND owner=?", (id, owner))
            conn.execute("DELETE FROM library_folders WHERE id=? AND owner=?", (id, owner))

    def change(self, owner, items, action, *, display_name=None, folder_id=None, allowed=None):
        if action == "rename":
            display_name = clean_name(display_name, 120)
        with self.workspace.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if action == "move":
                validate_folder(conn, owner, folder_id)
            # Validate the entire batch before changing a single item.
            for item in items:
                kind, id = item["kind"], identifier(item["id"])
                if allowed is not None and id not in allowed[kind]:
                    raise KeyError(id)
                table = "experiments" if kind == "run" else "datasets"
                row = conn.execute(f"SELECT payload FROM {table} WHERE id=?", (id,)).fetchone()
                if not row:
                    raise KeyError(id)
                record = json.loads(row[0])
                if (kind == "run" and record.get("job_kind", "development") != "development") or (kind == "upload" and record["source"] != "upload"):
                    raise KeyError(id)
                if action == "archive" and kind == "run" and record["status"] in ACTIVE:
                    raise ValueError("Queued, running, or cancelling runs cannot be archived. Wait for them to finish.")
            for item in items:
                kind, id = item["kind"], identifier(item["id"])
                conn.execute("INSERT OR IGNORE INTO library_items (owner,kind,id) VALUES (?,?,?)", (owner, kind, id))
                column, value = {"rename": ("display_name", display_name), "move": ("folder_id", folder_id),
                                 "archive": ("archived", 1), "restore": ("archived", 0)}[action]
                conn.execute(f"UPDATE library_items SET {column}=? WHERE owner=? AND kind=? AND id=?", (value, owner, kind, id))
