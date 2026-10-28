"""Explicitly trusted local replay packages; never an uploaded-model API."""
from pathlib import Path
from typing import Literal
import json

import joblib
from pydantic import Field

from app.experiments.provenance import source_digest
from app.experiments.validation import dependency_versions, file_digest
from app.faults.evaluator import FaultEvaluation, FixedDevelopmentEvaluator
from app.faults.scenarios import FaultCase, FaultPolicy, fingerprint
from app.schemas import Strict

FILES = {"context.joblib", "evaluation.json", "scenario.json"}
MAX_CONTEXT_BYTES = 64 * 1024 * 1024
MAX_JSON_BYTES = 16 * 1024 * 1024


class ReplayManifest(Strict):
    version: Literal[1] = 1
    context_fingerprint: str
    source_digest: str
    dependency_versions: dict[str, str]
    files: dict[str, str] = Field(min_length=3, max_length=3)


def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def read_json(path):
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("Replay JSON exceeds its size limit")
    return json.loads(path.read_text(encoding="utf-8"))


def export_evaluation(evaluator: FixedDevelopmentEvaluator, result: FaultEvaluation, directory: Path):
    """New local directories only. Context includes raw development data: do not publish it blindly."""
    directory = Path(directory)
    if evaluator.context_fingerprint != result.context_fingerprint or evaluator.policy.fingerprint != result.policy_fingerprint:
        raise ValueError("Evaluation does not belong to this fitted context and policy")
    if evaluator.evaluate(result.scenario).model_dump() != result.model_dump():
        raise ValueError("Evaluation differs from the recorded engine result")
    if source_digest() != result.source_digest:
        raise ValueError("Source changed during the investigation; do not export mixed provenance")
    directory.mkdir(parents=True, exist_ok=False)
    joblib.dump({"training": evaluator._training, "thresholds": evaluator.thresholds,
        "policy": evaluator.policy.model_dump(mode="json")}, directory / "context.joblib", compress=3)
    if (directory / "context.joblib").stat().st_size > MAX_CONTEXT_BYTES:
        raise ValueError("Fitted context exceeds the local replay size limit")
    write_json(directory / "evaluation.json", result.model_dump(mode="json"))
    write_json(directory / "scenario.json", result.scenario.model_dump(mode="json"))
    manifest = ReplayManifest(context_fingerprint=result.context_fingerprint, source_digest=result.source_digest,
        dependency_versions=dependency_versions(), files={name: file_digest(directory / name) for name in sorted(FILES)})
    write_json(directory / "manifest.pending.json", manifest.model_dump(mode="json"))
    (directory / "manifest.pending.json").replace(directory / "manifest.json")


def replay_evaluation(directory: Path, *, trusted=False) -> FaultEvaluation:
    if not trusted:
        raise ValueError("Explicit trust is required to load a locally produced Python model artifact")
    directory = Path(directory).resolve()
    for name in FILES | {"manifest.json"}:
        path = directory / name
        if path.is_symlink() or path.resolve().parent != directory or not path.is_file():
            raise ValueError("Replay files must be regular files inside the selected directory")
    manifest = ReplayManifest.model_validate(read_json(directory / "manifest.json"))
    if set(manifest.files) != FILES:
        raise ValueError("Unsupported replay manifest files")
    if manifest.source_digest != source_digest() or manifest.dependency_versions != dependency_versions():
        raise ValueError("Replay requires matching source and dependency versions")
    for name in FILES:
        path = directory / name
        if path.stat().st_size > (MAX_CONTEXT_BYTES if name == "context.joblib" else MAX_JSON_BYTES):
            raise ValueError("Replay file exceeds its size limit")
        if file_digest(path) != manifest.files[name]:
            raise ValueError("Replay file checksum does not match its manifest")
    expected = FaultEvaluation.model_validate(read_json(directory / "evaluation.json"))
    case = FaultCase.model_validate(read_json(directory / "scenario.json"))
    # Checksums detect accidental changes, not a malicious package. The caller's
    # explicit trust is necessary because joblib/Python model loading can execute code.
    payload = joblib.load(directory / "context.joblib")
    if not isinstance(payload, dict) or set(payload) != {"training", "thresholds", "policy"}:
        raise ValueError("Unsupported fitted context")
    evaluator = FixedDevelopmentEvaluator(payload["training"], payload["thresholds"], FaultPolicy.model_validate(payload["policy"]))
    if evaluator.context_fingerprint != manifest.context_fingerprint:
        raise ValueError("Restored fitted context does not reproduce its identity")
    actual = evaluator.evaluate(case)
    if fingerprint(actual.model_dump(mode="json")) != fingerprint(expected.model_dump(mode="json")):
        raise ValueError("Replay did not reproduce the original evaluation")
    return actual
