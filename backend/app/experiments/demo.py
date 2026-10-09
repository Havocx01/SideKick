"""Access and resource limits for the public synthetic-data demo."""

import hashlib
import os
import re
import secrets
import shutil
import threading
import time

from fastapi import HTTPException, Request

COOKIE = "sidekick_demo"
RETENTION = 24 * 60 * 60


def public_origin(request: Request) -> str:
    # Use deployment configuration, never an untrusted forwarded header.
    return (
        os.environ.get("SIDEKICK_PUBLIC_ORIGIN") or os.environ.get("RENDER_EXTERNAL_URL") or str(request.base_url)
    ).rstrip("/")


def session_token(request: Request) -> tuple[str, bool]:
    token = request.cookies.get(COOKIE, "")
    valid = bool(re.fullmatch(r"[a-f0-9]{64}", token))
    return (token if valid else secrets.token_hex(32)), not valid


def owner(request: Request) -> str:
    return hashlib.sha256(request.state.demo_token.encode()).hexdigest()


class DemoAccess:
    def __init__(self, workspace):
        self.workspace = workspace
        self.lock = threading.RLock()
        with workspace.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS demo_owners (
                    kind TEXT NOT NULL, id TEXT NOT NULL, owner TEXT NOT NULL,
                    created REAL NOT NULL, PRIMARY KEY (kind, id));
                CREATE TABLE IF NOT EXISTS demo_requests (
                    kind TEXT NOT NULL, owner TEXT NOT NULL, created REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS demo_requests_time ON demo_requests (created);
            """)

    def claim(self, kind: str, id: str, visitor: str):
        with self.workspace.connect() as conn:
            conn.execute("INSERT INTO demo_owners VALUES (?,?,?,?)", (kind, id, visitor, time.time()))

    def ids(self, kind: str, visitor: str) -> set[str]:
        with self.workspace.connect() as conn:
            return {
                row[0] for row in conn.execute("SELECT id FROM demo_owners WHERE kind=? AND owner=?", (kind, visitor))
            }

    def require(self, kind: str, id: str, visitor: str):
        if id not in self.ids(kind, visitor):
            raise HTTPException(
                404, "This item is unavailable in this browser or has expired. Start a new sample experiment."
            )

    def admit(self, kind: str, visitor: str):
        now = time.time()
        hourlyLimit = 6 if kind == "experiment" else 12
        with self.workspace.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM demo_requests WHERE created < ?", (now - RETENTION,))
            hourly, daily, personal = conn.execute(
                "SELECT SUM(created > ?), COUNT(*), SUM(owner=? AND created > ?) FROM demo_requests WHERE kind=?",
                (now - 3600, visitor, now - 3600, kind),
            ).fetchone()
            if (personal or 0) >= 2:
                raise HTTPException(
                    429,
                    "This browser has reached the limit of two new runs per hour. Explore the recorded benchmark or try again in an hour.",
                    headers={"Retry-After": "3600"},
                )
            if (hourly or 0) >= hourlyLimit or daily >= 24:
                raise HTTPException(
                    429,
                    "The shared demo has reached its training allowance. Explore the recorded benchmark or run Sidekick locally; the allowance resets within 24 hours.",
                    headers={"Retry-After": "86400"},
                )
            conn.execute("INSERT INTO demo_requests VALUES (?,?,?)", (kind, visitor, now))

    def sample(self, visitor: str):
        from app.experiments.datasets import sample

        with self.lock:
            existing = self.ids("datasets", visitor)
            if existing:
                return self.workspace.get("datasets", next(iter(existing)))
            self.admit("sample", visitor)
            record = sample(self.workspace, hosted=True, library_owner=f"demo:{visitor}")
            self.claim("datasets", record.dataset_id, visitor)
            return record

    def cleanup(self):
        # Only demo-owned, inactive records expire. Local uploads are never touched.
        with self.lock, self.workspace.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT kind,id FROM demo_owners WHERE created < ? ORDER BY kind DESC", (time.time() - RETENTION,)
            ).fetchall()
            for kind, id in rows:
                active = conn.execute(
                    "SELECT 1 FROM experiments WHERE status IN ('queued','running','cancelling') "
                    "AND (id=? OR json_extract(payload,'$.dataset_id')=?)",
                    (id, id),
                ).fetchone()
                if active:
                    continue
                # Retain a dataset until every experiment using it has also expired.
                if kind == "datasets":
                    referenced = conn.execute(
                        "SELECT 1 FROM experiments WHERE json_extract(payload,'$.dataset_id')=?", (id,)
                    ).fetchone()
                    if referenced:
                        continue
                path = self.workspace.directory(kind, id).resolve()
                if not path.is_relative_to(self.workspace.root):
                    raise ValueError("Demo cleanup path is outside the workspace")
                if path.exists():
                    shutil.rmtree(path)
                conn.execute(f"DELETE FROM {kind} WHERE id=?", (id,))
                library_kind = "upload" if kind == "datasets" else "run"
                conn.execute("DELETE FROM library_items WHERE kind=? AND id=?", (library_kind, id))
                conn.execute("DELETE FROM demo_owners WHERE kind=? AND id=?", (kind, id))
            conn.execute("UPDATE library_items SET folder_id=NULL WHERE folder_id IN "
                         "(SELECT id FROM library_folders WHERE owner LIKE 'demo:%' AND created_at < ?)", (time.time() - RETENTION,))
            conn.execute("DELETE FROM library_folders WHERE owner LIKE 'demo:%' AND created_at < ?", (time.time() - RETENTION,))
            conn.execute("DELETE FROM demo_requests WHERE created < ?", (time.time() - RETENTION,))
