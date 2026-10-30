"""Owned investigations executed by background workers."""
import asyncio
import json
from pathlib import Path
import re
import threading
import time

from app.faults.investigation import ExperimentRunner, InvestigationBudget, InvestigationStore
from app.faults.replay import load_trusted_context
from app.investigator.controller import ControllerLimits, NemotronController, controllerStatus
from app.investigator.findings import digest, loadCriterion, recordFindings, saveCriterion, summarize
from app.investigator.reduction import ensureTable as ensureReductions, reduce
from app.investigator.remedies import compareRemedy, ensureTable as ensureRemedies
from app.investigator.schemas import CleanMetrics, ContextInfo, InvestigationEvent, InvestigationSummary, InvestigationView, ProposalDetail
from app.investigator.search import seedSuite

NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class Conflict(RuntimeError):
    pass


def proposalDetail(item, payload):
    try:
        data = json.loads(payload)
    except ValueError:
        data = None
    if isinstance(data, dict) and "components" in data:
        data = {"scenario": data}
    data = data if isinstance(data, dict) else {}
    return ProposalDetail(id=item.id, sequence=item.seq, status=item.status, scenario=data.get("scenario") if isinstance(data.get("scenario"), dict) else None,
        reason=data.get("reason") if isinstance(data.get("reason"), str) else None,
        hypothesis=data.get("hypothesis") if isinstance(data.get("hypothesis"), dict) else None, rejection=item.reason)


class InvestigationService:
    def __init__(self, root: Path, settings):
        self.root = Path(root)
        self.contexts = self.root / "contexts"
        self.contexts.mkdir(parents=True, exist_ok=True)
        self.store = InvestigationStore(self.root / "store")
        self.settings = settings
        self.active: dict[str, tuple[str, threading.Thread]] = {}
        self.stopping = threading.Event()
        self.lock = threading.Lock()
        with self.store.transaction() as db:
            db.execute("CREATE TABLE IF NOT EXISTS investigation_owners(investigation TEXT PRIMARY KEY REFERENCES investigation_runs(id),"
                " owner TEXT NOT NULL, context TEXT NOT NULL, created REAL NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS investigation_events(id INTEGER PRIMARY KEY AUTOINCREMENT, investigation TEXT NOT NULL,"
                " kind TEXT NOT NULL, detail TEXT, request_id TEXT, created REAL NOT NULL, UNIQUE(investigation, request_id))")
            ensureReductions(db)
            ensureRemedies(db)
            # Workers do not survive a restart; their leases expire and the next start recovers the work.
            for (investigation,) in db.execute("SELECT DISTINCT investigation FROM investigation_events e WHERE kind LIKE 'started:%'"
                    " AND NOT EXISTS (SELECT 1 FROM investigation_events f WHERE f.investigation=e.investigation AND f.id>e.id"
                    " AND (f.kind LIKE 'finished:%' OR f.kind LIKE 'failed:%' OR f.kind='interrupted'))").fetchall():
                db.execute("INSERT INTO investigation_events(investigation,kind,detail,created) VALUES(?,?,?,?)",
                    (investigation, "interrupted", "The server restarted during this operation.", time.time()))

    def contextPath(self, name):
        if not NAME.match(name) or not (self.contexts / name / "manifest.json").is_file():
            raise KeyError("Unknown fitted context")
        return self.contexts / name

    def evaluator(self, name):
        # Only packages an operator placed in the server's context folder are loaded; uploads never reach here.
        return load_trusted_context(self.contextPath(name), trusted=True)

    def listContexts(self) -> list[ContextInfo]:
        contexts = []
        for path in sorted(self.contexts.iterdir()):
            if not NAME.match(path.name) or not (path / "manifest.json").is_file():
                continue
            engine = self.evaluator(path.name)
            clean = {name: CleanMetrics(detection=item.detection_fraction, alarmBurden=item.early_alarm_burden, medianLead=item.median_lead_time,
                histories=item.engines) for name, item in engine.cleanMetrics().items()}
            contexts.append(ContextInfo(name=path.name, contextFingerprint=engine.context_fingerprint,
                profile=engine.policy.profile.id if engine.policy.profile else None, sensors=list(engine.policy.allowed_sensors),
                thresholds=engine.thresholds, clean=clean))
        return contexts

    def event(self, investigation, kind, detail=None, requestId=None):
        with self.store.transaction() as db:
            db.execute("INSERT INTO investigation_events(investigation,kind,detail,request_id,created) VALUES(?,?,?,?,?)",
                (investigation, kind, detail[:300] if detail else None, requestId, time.time()))

    def owned(self, owner, investigation):
        with self.store.connection() as db:
            row = db.execute("SELECT owner, context, created FROM investigation_owners WHERE investigation=?", (investigation,)).fetchone()
        if row is None or row[0] != owner:
            raise KeyError("Unknown investigation")
        return row[1], row[2]

    def create(self, owner, request) -> str:
        engine = self.evaluator(request.context)
        if request.criterion is not None and request.criterion.candidate not in engine.thresholds:
            raise ValueError("Finding criterion must target one of the context's fixed models")
        budget = InvestigationBudget(max_experiments=request.maxExperiments, max_failures=min(request.maxFailures, request.maxExperiments),
            max_attempts_per_scenario=request.maxAttemptsPerScenario, max_run_seconds=request.maxRunSeconds)
        seeds = seedSuite(engine.policy, engine.config, request.seed) if request.seed else []
        investigation = self.store.create(engine, budget, seeds + request.proposals, objective=request.objective)
        with self.store.transaction() as db:
            db.execute("INSERT INTO investigation_owners VALUES(?,?,?,?)", (investigation, owner, request.context, time.time()))
        if request.criterion is not None:
            saveCriterion(self.store, investigation, request.criterion)
        self.event(investigation, "created", f"Context {request.context}")
        return investigation

    def summary(self, investigation, context, created) -> InvestigationSummary:
        state = self.store.load(investigation)
        findings = recordFindings(self.store, investigation) if loadCriterion(self.store, investigation) else []
        with self.lock:
            active = self.active.get(investigation, (None, None))[0]
        return InvestigationSummary(id=investigation, context=context, objective=self.store.get(investigation).objective, createdAt=created,
            active=active, stopReason=state.stop_reason, experimentsUsed=state.slots_used, maxExperiments=state.budget.max_experiments,
            discoveries=sum(finding.is_discovery for finding in findings))

    def list(self, owner) -> list[InvestigationSummary]:
        with self.store.connection() as db:
            rows = db.execute("SELECT investigation, context, created FROM investigation_owners WHERE owner=? ORDER BY created DESC", (owner,)).fetchall()
        return [self.summary(*row) for row in rows]

    def view(self, owner, investigation) -> InvestigationView:
        context, created = self.owned(owner, investigation)
        criterion = loadCriterion(self.store, investigation)
        findings = recordFindings(self.store, investigation) if criterion else []
        with self.store.connection() as db:
            events = [InvestigationEvent(sequence=seq, kind=kind, detail=detail, at=at) for seq, kind, detail, at in db.execute(
                "SELECT id, kind, detail, created FROM investigation_events WHERE investigation=? ORDER BY id", (investigation,))]
            reductions = [json.loads(row[0]) for row in db.execute("SELECT payload FROM reductions WHERE investigation=? ORDER BY created", (investigation,))]
            remedies = [json.loads(row[0]) for row in db.execute("SELECT payload FROM remedies WHERE investigation=? ORDER BY created", (investigation,))]
            payloads = dict(db.execute("SELECT id, payload FROM proposals WHERE investigation=?", (investigation,)).fetchall())
        state = self.store.load(investigation)
        proposals = [proposalDetail(item, payloads[item.id]) for item in state.proposals]
        return InvestigationView(**self.summary(investigation, context, created).model_dump(), state=state, proposals=proposals,
            criterion=criterion, findings=findings, discoveryFamilies=summarize(findings)["discoveryFamilies"],
            controller=controllerStatus(self.store, investigation), events=events, reductions=reductions, remedies=remedies)

    def submit(self, owner, investigation, kind, requestId, work):
        """Start background work once per request ID; a retried request never starts a second job."""
        context, _ = self.owned(owner, investigation)
        with self.lock:
            with self.store.transaction() as db:
                if db.execute("SELECT 1 FROM investigation_events WHERE investigation=? AND request_id=?", (investigation, requestId)).fetchone():
                    return False
                if investigation in self.active:
                    raise Conflict("Another operation is running for this investigation")
                db.execute("INSERT INTO investigation_events(investigation,kind,detail,request_id,created) VALUES(?,?,?,?,?)",
                    (investigation, f"started:{kind}", None, requestId, time.time()))
            thread = threading.Thread(target=self.work, args=(investigation, context, kind, work), daemon=True, name=f"investigation-{kind}")
            self.active[investigation] = (kind, thread)
        thread.start()
        return True

    def work(self, investigation, context, kind, work):
        try:
            detail = work(self.evaluator(context))
            self.event(investigation, f"finished:{kind}", detail)
        except Exception as error:  # A worker failure is recorded for the owner rather than lost in a thread.
            self.event(investigation, f"failed:{kind}", f"{type(error).__name__}: {error}")
        finally:
            with self.lock:
                self.active.pop(investigation, None)

    def start(self, owner, investigation, request, consent):
        if request.mode == "run":
            def work(engine):
                return ExperimentRunner(self.store, engine).run(investigation, cancelled=self.stopping.is_set).stop_reason
        else:
            if not request.allowProvider:
                raise PermissionError("Agent runs need explicit permission to send aggregate evidence to the provider")
            if not consent():
                raise PermissionError("Enable AI permission for this workspace and provider first")
            limits = ControllerLimits(maxCalls=request.maxProviderCalls, maxCompletionTokens=request.maxCompletionTokens)
            def work(engine):
                # Revoking permission stops the run and blocks a late reply from publishing.
                stop = lambda: self.stopping.is_set() or not consent()  # noqa: E731
                report = asyncio.run(NemotronController(self.store, engine, self.settings, limits).run(investigation, allowProvider=True, cancelled=stop))
                return report["stopReason"]
        return self.submit(owner, investigation, request.mode, request.requestId, work)

    def reduce(self, owner, investigation, request):
        def work(engine):
            return reduce(self.store, engine, request.attempt, maxExperiments=request.maxExperiments, cancelled=self.stopping.is_set)["status"]
        return self.submit(owner, investigation, "reduce", request.requestId, work)

    def remedy(self, owner, investigation, request):
        if request.kind == "augmented" and not request.approveTraining:
            raise PermissionError("Augmented retraining needs explicit approval")
        def work(engine):
            report = compareRemedy(self.store, engine, investigation, request.kind, threshold=request.threshold, approveTraining=request.approveTraining)
            return f"{report['improved']} improved, {report['degraded']} degraded"
        return self.submit(owner, investigation, "remedy", request.requestId, work)

    def cancel(self, owner, investigation):
        self.owned(owner, investigation)
        self.store.request_cancel(investigation)
        self.event(investigation, "cancel_requested")

    def resume(self, owner, investigation):
        self.owned(owner, investigation)
        with self.lock:
            if investigation in self.active:
                raise Conflict("Wait for the running operation to stop before resuming")
        self.store.resume(investigation)
        self.event(investigation, "resumed")

    def replay(self, owner, investigation, attempt):
        context, _ = self.owned(owner, investigation)
        if attempt not in {item.id for item in self.store.load(investigation).attempts}:
            raise KeyError("Unknown experiment attempt")
        recorded = self.store.result(attempt)
        rerun = self.evaluator(context).evaluate(recorded.scenario)
        expected = digest(recorded.model_dump(mode="json"))
        return {"attempt": attempt, "scenarioId": recorded.scenario_id, "matches": digest(rerun.model_dump(mode="json")) == expected,
            "evidenceDigest": expected}

    def export(self, owner, investigation):
        return self.view(owner, investigation).model_dump(mode="json")

    def wait(self, investigation, timeout=60):
        with self.lock:
            entry = self.active.get(investigation)
        if entry:
            entry[1].join(timeout)

    def close(self):
        self.stopping.set()
        with self.lock:
            threads = [thread for _, thread in self.active.values()]
        for thread in threads:
            thread.join(10)
