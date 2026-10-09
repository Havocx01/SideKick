import hashlib
import json
from urllib.parse import urlencode

from app.assistant.investigation import EvidenceTools, toolSpec
from app.assistant.schemas import AnalysisFinding, AnalysisResult, EvidenceReference
from app.data.contract import infer_mapping
from app.experiments.datasets import read_csv, validated_dataset
from app.schemas import DatasetRegistration


def reviewData(workspace, context):
    record = DatasetRegistration.model_validate(workspace.get("datasets", context.dataset_id))
    path = workspace.directory("datasets", context.dataset_id) / "data.csv"
    frame = read_csv(path)
    try:
        suggestion = infer_mapping(frame)
    except ValueError:
        suggestion = None
    mapping = record.mapping if record.confirmed else context.mapping or suggestion
    complete = record.complete_histories if record.confirmed else context.complete_histories
    sources, findings = [], []
    href = "/new?" + urlencode({"source": "sample" if record.source == "synthetic" else "upload", "dataset": record.dataset_id})

    def addSource(metric, value, unit, label):
        source = EvidenceReference(id=f"d{len(sources)}", candidate="dataset", partition=context.partition, metric=metric,
            value=str(value), unit=unit, label=label, display="Yes" if value is True else "No" if value is False else str(value),
            context="Dataset review · Current mapping", href=href)
        sources.append(source)
        return source.id

    sizeRefs = [addSource("row_count", len(frame), "readings", "Readings"), addSource("column_count", len(frame.columns), "columns", "Columns")]
    findings.append(AnalysisFinding(id="data-size", title="Data received", detail=f"{len(frame):,} readings across {len(frame.columns)} columns.", source_ids=sizeRefs))
    profile = None
    valid = False
    error = "Choose equipment ID, cycle index and sensor columns before validating the data."
    if mapping:
        assigned = [mapping.equipment_id, mapping.cycle_index, *mapping.sensors]
        if mapping.failure_cycle:
            assigned.append(mapping.failure_cycle)
        mapping = mapping.model_copy(update={"ignored": [column for column in frame.columns if column not in assigned]})
        try:
            dataset = validated_dataset(path, mapping, complete, id=record.dataset_id, source=record.source)
            from app.data.profiler import profile_dataset
            profile = profile_dataset(dataset)
            valid = True
        except ValueError as failure:
            error = str(failure)
    validationRef = addSource("mapping_valid", valid, "boolean", "Current mapping passes validation")
    findings.insert(0, AnalysisFinding(id="data-validation", title="Ready for mapping confirmation" if valid else "Data needs attention",
        detail="The current mapping passes Sidekick's data checks. Review the roles and failure labels before training." if valid else error,
        tone="success" if valid else "danger", source_ids=[validationRef]))
    if profile:
        addSource("equipment_count", profile.equipment_count, "histories", "Equipment histories")
        for issue in profile.findings:
            ref = addSource("profile_finding", issue.code, "check", "Data check")
            findings.append(AnalysisFinding(id=f"data-{issue.code.lower()}", title=issue.code.replace("_", " ").capitalize(), detail=issue.message,
                source_ids=[ref], tone="warning" if issue.severity.value == "warning" else "neutral"))
    mappingRef = addSource("mapping_suggestion_available", suggestion is not None and not record.confirmed, "boolean", "Editable mapping suggestion available")
    findings.append(AnalysisFinding(id="data-mapping", title="Review column roles", detail="Column names and numeric types suggest this draft mapping. Verify it against your equipment records."
        if suggestion and not record.confirmed else "The confirmed mapping is fixed." if record.confirmed else "Column roles could not be inferred. Assign them manually.", source_ids=[mappingRef]))
    payload = {"file": hashlib.sha256(path.read_bytes()).hexdigest(), "context": context.model_dump(mode="json"),
               "confirmed": record.confirmed, "mapping": mapping.model_dump() if mapping else None, "valid": valid}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    result = AnalysisResult(title="Data review", summary=findings[0].detail, findings=findings, sources=sources, actions=[],
        limitations=["Validation checks the file and mapping, not whether equipment actually failed.", "Observed failure labels must be confirmed by the equipment owner.",
                     "Mapping suggestions only edit the draft. Validation and training remain explicit actions."],
        evidence_digest=digest, suggested_mapping=suggestion if not record.confirmed else None)
    columns = {f"column-{i + 1}": column for i, column in enumerate(frame.columns)}
    descriptors = [{"column": alias, "numeric": bool(frame[column].dtype.kind in "biufc"), "missing_fraction": float(frame[column].isna().mean())}
                   for alias, column in columns.items()]
    return result, descriptors, columns


class DataTools(EvidenceTools):
    def __init__(self, result, context, descriptors, columns):
        self.result = result.model_copy(deep=True)
        self.result.assessment = []
        self.result.investigation = []
        self.context = context
        self.models = {"data-1": "dataset"}
        self.cases = {}
        self.claims = {}
        self.seenFindings = set()
        self.seenActions = set()
        self.calls = []
        self.descriptors = descriptors
        self.columns = columns

    def fresh(self):
        return DataTools(self.result, self.context, self.descriptors, self.columns)

    @property
    def specs(self):
        return [toolSpec("get_dataset_checks"), toolSpec("suggest_column_mapping")]

    def intro(self):
        return {"task": "data", "columns": self.descriptors, "mapping_requires_confirmation": True}

    def get_dataset_checks(self):
        validation = next(source for source in self.result.sources if source.metric == "mapping_valid")
        valid = validation.value == "True"
        finding = next(f for f in self.result.findings if f.id == "data-validation")
        count = next((source for source in self.result.sources if source.metric == "equipment_count"), None)
        text = (f"The current mapping passes file and training-readiness checks for {count.display} equipment histories. " if valid and count else
                "The current mapping passes file and training-readiness checks. " if valid else f"Training is blocked: {finding.detail} ")
        text += "Confirm the column roles and observed failure records before training." if valid else "Correct this issue and validate again; do not invent failure labels."
        claim = self.claim("data-readiness", text, [validation.id] + ([count.id] if count else []))
        claims = [claim]
        checks = [f for f in self.result.findings if f.id not in ("data-validation", "data-mapping", "data-size")]
        checks.sort(key=lambda f: (f.tone not in ("danger", "warning"), f.id != "data-fault_eligible_channels"))
        for issue in checks:
            claims.append(self.claim(f"data-issue-{issue.id}", issue.detail, issue.source_ids))
        return self.expose([finding for finding in self.result.findings if finding.id != "data-mapping"], claims)

    def suggest_column_mapping(self):
        mapping = self.result.suggested_mapping
        roles = {}
        if mapping:
            byName = {name: alias for alias, name in self.columns.items()}
            roles = {"equipment_id": byName[mapping.equipment_id], "cycle_index": byName[mapping.cycle_index],
                     "sensors": [byName[name] for name in mapping.sensors], "failure_cycle": byName.get(mapping.failure_cycle),
                     "uncertain_columns": [byName[name] for name in mapping.ambiguous]}
        finding = next(finding for finding in self.result.findings if finding.id == "data-mapping")
        claim = self.claim("mapping-review", "Review the suggested column roles against your records. The suggestion does not confirm failure histories." if mapping
                           else "No editable mapping suggestion is available. Review the current roles manually.", finding.source_ids)
        return self.expose([finding], [claim], {"suggested_roles": roles})

    def local(self):
        checks = self.call("get_dataset_checks", {})
        mapping = self.call("suggest_column_mapping", {})
        return self.finish([checks["finding_ids"][0], "data-mapping"], checks["claims"][:2] + mapping["claims"], None, None)
