"""SQLite metadata for analysis jobs, consent and presenter access."""
import json
import re
import sqlite3
import time
from pathlib import Path

from pydantic import ValidationError

from app.assistant.schemas import AnalysisRecord

RESULT_GROWTH_BYTES = 16_384
# JSON escapes can require six bytes per character, more than UTF-8 alone.
DRAFT_BYTES = 12_000 * 6


class AnalysisCapacityError(RuntimeError):
    pass


class AnalysisRevokedError(PermissionError):
    pass


class AssistantStore:
    def __init__(self, root: Path, *, max_public_records=2000, max_public_bytes=32 * 1024 * 1024):
        self.max_public_records = max_public_records
        self.max_public_bytes = max_public_bytes
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "assistant.sqlite3"
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for statement in (
                "CREATE TABLE IF NOT EXISTS analyses(id TEXT PRIMARY KEY, owner TEXT NOT NULL, payload TEXT NOT NULL)",
                "CREATE TABLE IF NOT EXISTS consent(owner TEXT, experiment TEXT, allowed INTEGER, PRIMARY KEY(owner,experiment))",
                "CREATE TABLE IF NOT EXISTS sessions(owner TEXT PRIMARY KEY, unlocked_until REAL NOT NULL)",
                "CREATE TABLE IF NOT EXISTS attempts(address TEXT NOT NULL, created REAL NOT NULL)",
                "CREATE TABLE IF NOT EXISTS analysis_provenance(id TEXT PRIMARY KEY, result_origin TEXT NOT NULL, brief_origin TEXT NOT NULL)",
            ):
                db.execute(statement)
            if "revoked" not in {row[1] for row in db.execute("PRAGMA table_info(analysis_provenance)")}:
                db.execute("ALTER TABLE analysis_provenance ADD COLUMN revoked INTEGER NOT NULL DEFAULT 0")
            if "public" not in {row[1] for row in db.execute("PRAGMA table_info(analyses)")}:
                db.execute("ALTER TABLE analyses ADD COLUMN public INTEGER NOT NULL DEFAULT 0")
            if "reserved_bytes" not in {row[1] for row in db.execute("PRAGMA table_info(analyses)")}:
                db.execute("ALTER TABLE analyses ADD COLUMN reserved_bytes INTEGER NOT NULL DEFAULT 0")
            rows = db.execute("SELECT id,payload FROM analyses").fetchall()
            for id, payload in rows:
                # Read the original JSON before an older result contract is discarded.
                result_origin, brief_origin = self._origins(payload)
                db.execute("INSERT OR IGNORE INTO analysis_provenance(id,result_origin,brief_origin) VALUES(?,?,?)", (id, result_origin, brief_origin))
                try:
                    record = AnalysisRecord.model_validate_json(payload)
                except ValidationError:
                    record = self.upgrade(payload)
                    if record is None:
                        # Keep unrecognised historical payloads and account for their bytes.
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

    @staticmethod
    def _origins(payload):
        try:
            data = json.loads(payload)
            result = data.get("result")
            origin = "cloud" if isinstance(result, dict) and result.get("mode") == "ai" else "evidence" if isinstance(result, dict) and result.get("mode") == "evidence" else "unknown"
            return origin, origin if data.get("brief_text") is not None else "unknown"
        except (ValueError, TypeError, AttributeError):
            return "unknown", "unknown"

    def provenance(self, id, owner):
        with self.connect() as db:
            row = db.execute("SELECT p.result_origin,p.brief_origin FROM analysis_provenance p JOIN analyses a ON a.id=p.id WHERE a.id=? AND a.owner=?", (id, owner)).fetchone()
        return row or ("unknown", "unknown")

    def revoked(self, id, owner):
        with self.connect() as db:
            row = db.execute("SELECT p.revoked FROM analysis_provenance p JOIN analyses a ON a.id=p.id WHERE a.id=? AND a.owner=?", (id, owner)).fetchone()
        return bool(row and row[0])

    def save(self, record: AnalysisRecord, owner: str, public: bool = False, *, brief_origin=None):
        payload = record.model_dump_json()
        size = len(payload.encode("utf-8"))
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT owner,public,reserved_bytes,payload FROM analyses WHERE id=?", (record.id,)).fetchone()
            result_origin = "cloud" if record.result and record.result.mode == "ai" else "evidence" if record.result else "unknown"
            if existing:
                if existing[0] != owner:
                    raise KeyError(record.id)
                tombstone = db.execute("SELECT revoked FROM analysis_provenance WHERE id=?", (record.id,)).fetchone()
                if tombstone and tombstone[0]:
                    # HTTP checks can race with revocation. Enforce this inside the write lock.
                    raise AnalysisRevokedError("This analysis was revoked. Start a fresh analysis before saving or exporting a review.")
                # Previously admitted and legacy records remain editable at capacity.
                if existing[1] and existing[2] and size > existing[2]:
                    raise ValueError("Analysis exceeds its reserved payload capacity.")
                prior = db.execute("SELECT result_origin,brief_origin FROM analysis_provenance WHERE id=?", (record.id,)).fetchone() or self._origins(existing[3])
                previous_brief = json.loads(existing[3]).get("brief_text")
                # Editing never declassifies a cloud-derived or unknown draft.
                retained_brief_origin = prior[1] if previous_brief is not None else result_origin
                if record.brief_text != previous_brief and result_origin == "cloud":
                    retained_brief_origin = "cloud"
                if record.brief_text is None:
                    retained_brief_origin = "unknown"
                db.execute("INSERT INTO analysis_provenance(id,result_origin,brief_origin) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET result_origin=excluded.result_origin,brief_origin=excluded.brief_origin", (record.id, result_origin, brief_origin or retained_brief_origin))
                db.execute("UPDATE analyses SET payload=? WHERE id=?", (payload, record.id))
                return
            reserved = size + RESULT_GROWTH_BYTES + DRAFT_BYTES if public else 0
            if public:
                self._expire(db)
                # Legacy rows have no trustworthy mode marker. Count them without deleting them.
                count, used = db.execute("SELECT COUNT(*),COALESCE(SUM(MAX(reserved_bytes,length(CAST(payload AS BLOB)))),0) FROM analyses").fetchone()
                if count >= self.max_public_records or used + reserved > self.max_public_bytes:
                    raise AnalysisCapacityError("The shared demo is temporarily at storage capacity. Saved analyses remain available. Try again later or run Sidekick locally.")
            db.execute("INSERT INTO analyses(id,owner,payload,public,reserved_bytes) VALUES(?,?,?,?,?)", (record.id, owner, payload, int(public), reserved))
            db.execute("INSERT INTO analysis_provenance(id,result_origin,brief_origin) VALUES(?,?,?)", (record.id, result_origin, brief_origin or (result_origin if record.brief_text is not None else "unknown")))

    def get(self, id: str, owner: str) -> AnalysisRecord:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM analyses WHERE id=? AND owner=?", (id, owner)).fetchone()
        if not row:
            raise KeyError(id)
        try:
            return AnalysisRecord.model_validate_json(row[0])
        except ValidationError:
            raise KeyError(id) from None

    def convert_review(self, converted: AnalysisRecord, owner: str) -> AnalysisRecord:
        """Convert a view while retaining the latest draft and its independent provenance."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload,public,reserved_bytes FROM analyses WHERE id=? AND owner=?", (converted.id, owner)).fetchone()
            if not row:
                raise KeyError(converted.id)
            current = AnalysisRecord.model_validate_json(row[0])
            if row[1] and current.created_at < time.time() - 86400:
                raise KeyError(converted.id)
            if current.status != "completed":
                raise ValueError("Wait for the investigation to finish.")
            if current.context.model_copy(update={"task": "brief"}) != converted.context:
                raise ValueError("The analysis context changed. Reopen it before preparing a review.")
            origins = db.execute("SELECT result_origin,brief_origin,revoked FROM analysis_provenance WHERE id=?", (converted.id,)).fetchone() or ("unknown", "unknown", 0)
            if origins[2] and not (current.brief_text is not None and origins[1] == "evidence" and converted.result and converted.result.mode == "evidence"):
                raise AnalysisRevokedError("This analysis was revoked. Start a fresh analysis before preparing a review.")
            # Replace only the derived view; a concurrent explicit save/autosave wins.
            current.context = converted.context
            current.result = converted.result
            current.updated_at = time.time()
            payload = current.model_dump_json()
            if row[1] and row[2] and len(payload.encode("utf-8")) > row[2]:
                raise ValueError("Analysis exceeds its reserved payload capacity.")
            db.execute("UPDATE analyses SET payload=? WHERE id=?", (payload, current.id))
            result_origin = "cloud" if current.result and current.result.mode == "ai" else "evidence" if current.result else "unknown"
            db.execute("UPDATE analysis_provenance SET result_origin=? WHERE id=?", (result_origin, current.id))
            return current

    def expired(self, id, owner):
        with self.connect() as db:
            row = db.execute("SELECT public,payload FROM analyses WHERE id=? AND owner=?", (id, owner)).fetchone()
        return bool(row and row[0] and json.loads(row[1])["created_at"] < time.time() - 86400)

    def latest(self, owner: str, fingerprint: str) -> AnalysisRecord | None:
        """Reuse eligible active or complete jobs for this visitor and evidence."""
        with self.connect() as db:
            rows = db.execute('''SELECT payload FROM analyses WHERE owner=? AND json_valid(payload)
                AND id NOT IN (SELECT id FROM analysis_provenance WHERE revoked=1)
                AND json_extract(payload,'$.cache_fingerprint')=?
                AND json_extract(payload,'$.status') IN ('queued','running','completed')
                AND json_type(payload,'$.result')='object'
                AND (public=0 OR json_extract(payload,'$.created_at') >= ?)
                ORDER BY json_extract(payload,'$.created_at') DESC''',
                (owner, fingerprint, time.time() - 86400)).fetchall()
        for row in rows:
            try:
                return AnalysisRecord.model_validate_json(row[0])
            except ValidationError:
                continue
        return None

    def consent(self, owner: str, experiment: str) -> bool:
        with self.connect() as db:
            row = db.execute("SELECT allowed FROM consent WHERE owner=? AND experiment=?", (owner, experiment)).fetchone()
        return bool(row and row[0])

    def latest_scoped(self, owner, draft_fingerprint):
        """A version change does not authorise a new paid analysis of identical evidence."""
        with self.connect() as db:
            rows = db.execute('''SELECT payload FROM analyses WHERE owner=? AND json_valid(payload)
                AND id NOT IN (SELECT id FROM analysis_provenance WHERE revoked=1)
                AND json_extract(payload,'$.draft_fingerprint')=?
                AND json_extract(payload,'$.status')='completed'
                AND (public=0 OR json_extract(payload,'$.created_at') >= ?)
                ORDER BY json_extract(payload,'$.updated_at') DESC''',
                (owner, draft_fingerprint, time.time() - 86400)).fetchall()
        for row in rows:
            try:
                return AnalysisRecord.model_validate_json(row[0])
            except ValidationError:
                continue
        return None

    def latest_draft(self, owner: str, fingerprint: str, evidence_digest: str, context) -> AnalysisRecord | None:
        """Retain human edits across prompt updates, only for identical scoped evidence."""
        with self.connect() as db:
            rows = db.execute('''SELECT payload FROM analyses WHERE owner=? AND json_valid(payload)
                AND id NOT IN (SELECT id FROM analysis_provenance WHERE revoked=1 AND brief_origin!='evidence')
                AND (json_extract(payload,'$.draft_fingerprint')=? OR json_extract(payload,'$.draft_fingerprint') IS NULL)
                AND json_extract(payload,'$.status')='completed'
                AND json_type(payload,'$.brief_text')='text'
                AND (public=0 OR json_extract(payload,'$.created_at') >= ?)
                ORDER BY json_extract(payload,'$.updated_at') DESC''',
                (owner, fingerprint, time.time() - 86400))
            for row in rows:
                try:
                    saved = AnalysisRecord.model_validate_json(row[0])
                except ValidationError:
                    continue
                if saved.draft_fingerprint == fingerprint:
                    return saved
                # Legacy identity is accepted only after exact evidence and scoped context verification.
                legacy = re.fullmatch(r"sidekick-[a-zA-Z0-9.\-]+:([a-f0-9]{64})", saved.cache_fingerprint or "")
                verified_digest = legacy.group(1) if legacy else saved.result.evidence_digest if saved.result else None
                if verified_digest == evidence_digest:
                    from app.assistant.service import normalized_context
                    if normalized_context(saved.context) == normalized_context(context):
                        return saved
        return None

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

    def revoke_results(self, owner: str, experiment: str):
        """Discard cloud interpretations so opting in later never resurrects old output."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR REPLACE INTO consent VALUES(?,?,0)", (owner, experiment))
            for id, payload in db.execute("SELECT id,payload FROM analyses WHERE owner=?", (owner,)).fetchall():
                try:
                    record = AnalysisRecord.model_validate_json(payload)
                except ValidationError:
                    continue
                origins = db.execute("SELECT result_origin,brief_origin FROM analysis_provenance WHERE id=?", (id,)).fetchone() or ("unknown", "unknown")
                if record.context.consent_scope == experiment:
                    tainted = origins[0] != "evidence" or (record.brief_text is not None and origins[1] != "evidence") or record.status in {"queued", "running"}
                    if origins[0] != "evidence":
                        record.result = None
                    if origins[1] != "evidence":
                        record.brief_text = None
                        record.brief_saved_at = None
                    if record.status in {"queued", "running"}:
                        record.status = "cancelled"
                        for stage in record.stages:
                            stage.status = "failed"
                    record.error = "Cloud consent was revoked. Showing recorded evidence."
                    record.updated_at = time.time()
                    db.execute("UPDATE analyses SET payload=? WHERE id=?", (record.model_dump_json(), id))
                    # Retain a tombstone so late autosaves cannot declassify revoked text,
                    # including after consent is granted again.
                    if tainted:
                        db.execute("UPDATE analysis_provenance SET revoked=1 WHERE id=?", (id,))


    def expire_public(self):
        """Expire public analysis records without limiting new requests."""
        with self.connect() as db:
            self._expire(db)

    @staticmethod
    def _expire(db):
        db.execute("DELETE FROM analyses WHERE public=1 AND json_valid(payload) AND json_extract(payload,'$.created_at') < ? AND json_extract(payload,'$.status') NOT IN ('queued','running')", (time.time() - 86400,))
        db.execute("DELETE FROM analysis_provenance WHERE id NOT IN (SELECT id FROM analyses)")
