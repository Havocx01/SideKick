"""SQLite metadata for analysis jobs, consent and atomic usage limits."""
import json
import sqlite3
import time
from pathlib import Path

from pydantic import ValidationError

from app.assistant.schemas import AnalysisRecord


class PublicLimitError(ValueError):
    pass

class AssistantStore:
    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "assistant.sqlite3"
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS analyses(id TEXT PRIMARY KEY, owner TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS consent(owner TEXT, experiment TEXT, allowed INTEGER, PRIMARY KEY(owner,experiment));
                CREATE TABLE IF NOT EXISTS sessions(owner TEXT PRIMARY KEY, unlocked_until REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS usage(owner TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS attempts(address TEXT NOT NULL, created REAL NOT NULL);
            ''')
            if "public" not in {row[1] for row in db.execute("PRAGMA table_info(analyses)")}:
                db.execute("ALTER TABLE analyses ADD COLUMN public INTEGER NOT NULL DEFAULT 0")
            rows = db.execute("SELECT id,payload FROM analyses").fetchall()
            for id, payload in rows:
                try:
                    record = AnalysisRecord.model_validate_json(payload)
                except ValidationError:
                    record = self.upgrade(payload)
                    if record is None:
                        db.execute("DELETE FROM analyses WHERE id=?", (id,))
                        continue
                    db.execute("UPDATE analyses SET payload=? WHERE id=?", (record.model_dump_json(), id))
                if record.status in {"queued", "running"}:
                    record.status = "interrupted"
                    record.error = "Server restarted. Start a new analysis."
                    record.updated_at = time.time()
                    db.execute("UPDATE analyses SET payload=? WHERE id=?", (record.model_dump_json(), id))

    @staticmethod
    def upgrade(payload: str) -> AnalysisRecord | None:
        """Drop results saved by an older contract; reads rebuild them from recorded evidence."""
        try:
            data = json.loads(payload)
            data["result"] = None
            return AnalysisRecord.model_validate(data)
        except (ValueError, TypeError):
            return None

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def save(self, record: AnalysisRecord, owner: str, public: bool = False):
        with self.connect() as db:
            db.execute("INSERT INTO analyses(id,owner,payload,public) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload", (record.id, owner, record.model_dump_json(), int(public)))

    def get(self, id: str, owner: str) -> AnalysisRecord:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM analyses WHERE id=? AND owner=?", (id, owner)).fetchone()
        if not row:
            raise KeyError(id)
        return AnalysisRecord.model_validate_json(row[0])

    def consent(self, owner: str, experiment: str) -> bool:
        with self.connect() as db:
            row = db.execute("SELECT allowed FROM consent WHERE owner=? AND experiment=?", (owner, experiment)).fetchone()
        return bool(row and row[0])

    def set_consent(self, owner: str, experiment: str, allowed: bool):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO consent VALUES(?,?,?)", (owner, experiment, int(allowed)))

    def unlocked(self, owner: str) -> bool:
        with self.connect() as db:
            row = db.execute("SELECT unlocked_until FROM sessions WHERE owner=?", (owner,)).fetchone()
        return bool(row and row[0] > time.time())

    def unlock(self, owner: str):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO sessions VALUES(?,?)", (owner, time.time() + 8 * 3600))

    def attempt(self, address: str):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM attempts WHERE created < ?", (time.time() - 900,))
            if db.execute("SELECT COUNT(*) FROM attempts WHERE address=?", (address,)).fetchone()[0] >= 5:
                raise ValueError("Too many access attempts. Try again in 15 minutes.")
            db.execute("INSERT INTO attempts VALUES(?,?)", (address, time.time()))

    def admit(self, owner: str, session_limit: int, daily_limit: int):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            daily = db.execute("SELECT COUNT(*) FROM usage WHERE created > ?", (time.time() - 86400,)).fetchone()[0]
            personal = db.execute("SELECT COUNT(*) FROM usage WHERE owner=?", (owner,)).fetchone()[0]
            if daily >= daily_limit or personal >= session_limit:
                raise ValueError("Live analysis allowance reached. Recorded evidence is still available.")
            db.execute("INSERT INTO usage VALUES(?,?)", (owner, time.time()))
    def revoke_results(self, owner: str, experiment: str):
        """Discard cloud interpretations so opting in later never resurrects old output."""
        with self.connect() as db:
            for id, payload in db.execute("SELECT id,payload FROM analyses WHERE owner=?", (owner,)).fetchall():
                record = AnalysisRecord.model_validate_json(payload)
                if record.context.consent_scope == experiment and record.result and record.result.mode == "ai":
                    record.result = None
                    record.brief_text = None
                    record.brief_saved_at = None
                    record.error = "Cloud consent was revoked. Showing recorded evidence."
                    record.updated_at = time.time()
                    db.execute("UPDATE analyses SET payload=? WHERE id=?", (record.model_dump_json(), id))


    def admit_evidence(self, owner: str):
        """Bound public deterministic work and expire public analysis records."""
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM analyses WHERE public=1 AND json_extract(payload,'$.created_at') < ?", (now - 86400,))
            total, personal = db.execute("SELECT COUNT(*),SUM(owner=?) FROM analyses WHERE public=1 AND json_extract(payload,'$.created_at') > ?", (owner, now - 3600)).fetchone()
            if total >= 300 or (personal or 0) >= 30:
                raise PublicLimitError("Analysis allowance reached. Try again in an hour.")

