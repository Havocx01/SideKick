"""The copilot's tool surface.

The copilot has no direct access to data or models. It can only call these six
tools, each with a JSON schema the arguments are validated against, and each
returning a structured result drawn from the evidence store. Raw sensor files stay
server-side; the model sees summaries and metrics, never the readings.

The division of labour is deliberate. The copilot maps columns, translates a
stated alert requirement into settings, triggers work and drafts prose. It does
not produce predictions, and it does not compute metrics. Separate machine-learning
models produce predictions; these tools return numbers that were already computed
and recorded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.schemas import CLEAN_SCENARIO_ID, EvidenceBundle

ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    mutating: bool = False

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolError(RuntimeError):
    """A tool refused the request. The message is shown to the user."""


def _string(schema_properties: dict, name: str, arguments: dict, *, required: bool = True) -> str | None:
    value = arguments.get(name)
    if value is None:
        if required:
            raise ToolError(f"{name} is required")
        return None
    if not isinstance(value, str):
        raise ToolError(f"{name} must be a string")
    return value


class ToolRegistry:
    """The six tools, bound to one evidence bundle.

    Read-only against a bundle. Tools that would start work return a description
    of what would run plus the command to run it, rather than launching training
    inside a request; the hosted service has neither the memory nor the time
    budget, and pretending otherwise would be the wrong demo.
    """

    def __init__(self, bundle: EvidenceBundle, *, allow_training: bool = False) -> None:
        self.bundle = bundle
        self.allow_training = allow_training
        self._tools = {tool.name: tool for tool in self._build()}

    # -- registry ----------------------------------------------------------

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise ToolError(f"unknown tool {name!r}")
        return self._tools[name]

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.openai_schema() for tool in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools)

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.get(name).handler(arguments or {})

    # -- tool implementations ---------------------------------------------

    def _build(self) -> list[Tool]:
        return [
            Tool(
                name="profile_dataset",
                description=(
                    "Return the data quality profile for the loaded dataset: row and "
                    "equipment counts, per-channel statistics, which channels are "
                    "constant, and every quality finding with its severity. Call this "
                    "before discussing whether the data can be evaluated."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "include_channels": {
                            "type": "boolean",
                            "description": "Include per-channel statistics. Defaults to false.",
                        }
                    },
                    "additionalProperties": False,
                },
                handler=self._profile_dataset,
            ),
            Tool(
                name="map_columns",
                description=(
                    "Return the confirmed mapping of uploaded columns onto the roles "
                    "the pipeline requires, including any column the profiler could "
                    "not assign confidently. Use this when the user asks what a column "
                    "is being treated as."
                ),
                parameters={"type": "object", "properties": {}, "additionalProperties": False},
                handler=self._map_columns,
            ),
            Tool(
                name="train_candidates",
                description=(
                    "Describe the training configuration: the candidates, the "
                    "partitions, the horizon and the alert rule. Returns the command "
                    "that runs training locally. Does not train during a conversation."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "horizon_cycles": {
                            "type": "integer",
                            "description": "Warning horizon in operating cycles.",
                            "minimum": 1,
                        },
                        "min_detection_fraction": {
                            "type": "number",
                            "description": "Required share of failures detected in the useful window.",
                            "minimum": 0,
                            "maximum": 1,
                        },
                        "max_early_alarm_burden": {
                            "type": "number",
                            "description": "Permitted share of healthy cycles spent in alarm.",
                            "minimum": 0,
                            "maximum": 1,
                        },
                    },
                    "additionalProperties": False,
                },
                handler=self._train_candidates,
                mutating=True,
            ),
            Tool(
                name="run_fault_tests",
                description=(
                    "Summarise the sensor-fault scenarios that were run and how each "
                    "candidate held up: the required selection set, the wider reported "
                    "matrix, and which case hurt a candidate most."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "candidate": {
                            "type": "string",
                            "description": "Restrict to one candidate family, e.g. 'xgboost'.",
                        },
                        "required_only": {
                            "type": "boolean",
                            "description": "Only the bounded set used for selection. Defaults to true.",
                        },
                    },
                    "additionalProperties": False,
                },
                handler=self._run_fault_tests,
            ),
            Tool(
                name="query_runs",
                description=(
                    "Look up recorded results. Returns measured metrics for candidates "
                    "and scenarios, with the run identifier that produced each one. "
                    "Every number you state must come from this tool or from "
                    "run_fault_tests."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "candidate": {"type": "string", "description": "Candidate family or 'all'."},
                        "scenario_id": {
                            "type": "string",
                            "description": "Scenario identifier, or 'clean' for unfaulted results.",
                        },
                        "metric": {
                            "type": "string",
                            "description": "Restrict to one metric name.",
                        },
                        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    },
                    "additionalProperties": False,
                },
                handler=self._query_runs,
            ),
            Tool(
                name="draft_report",
                description=(
                    "Return the structured evidence needed to write the decision "
                    "report: the criteria, the ranking, the recommendation or the "
                    "absence of one, the partitions, the configuration fingerprint and "
                    "the stated limitations."
                ),
                parameters={"type": "object", "properties": {}, "additionalProperties": False},
                handler=self._draft_report,
            ),
        ]

    # -- handlers ----------------------------------------------------------

    def _profile_dataset(self, arguments: dict[str, Any]) -> dict[str, Any]:
        profile = self.bundle.profile
        payload: dict[str, Any] = {
            "dataset_id": profile.dataset_id,
            "source": profile.source,
            "data_hash": profile.data_hash,
            "rows": profile.row_count,
            "equipment_count": profile.equipment_count,
            "cycles_min": profile.min_cycles,
            "cycles_median": profile.median_cycles,
            "cycles_max": profile.max_cycles,
            "positive_label_fraction": profile.positive_label_fraction,
            "usable": profile.usable,
            "constant_channels": [s.name for s in profile.sensors if s.constant],
            "fault_eligible_channels": profile.varying_sensors,
            "findings": [
                {"code": f.code, "severity": f.severity.value, "message": f.message}
                for f in profile.findings
            ],
        }
        if arguments.get("include_channels"):
            payload["channels"] = [
                {
                    "name": s.name,
                    "mean": s.mean,
                    "std": s.std,
                    "missing_fraction": s.missing_fraction,
                    "constant": s.constant,
                }
                for s in profile.sensors
            ]
        return payload

    def _map_columns(self, arguments: dict[str, Any]) -> dict[str, Any]:
        profile = self.bundle.profile
        return {
            "dataset_id": profile.dataset_id,
            "note": (
                "Roles were confirmed when the dataset was loaded. Sensor models see "
                "only sensor-derived features; equipment identity, cycle count and "
                "remaining life are excluded from the design matrix."
            ),
            "sensor_channels": len(profile.sensors),
            "fault_eligible_channels": profile.varying_sensors,
            "constant_channels": [s.name for s in profile.sensors if s.constant],
        }

    def _train_candidates(self, arguments: dict[str, Any]) -> dict[str, Any]:
        config = self.bundle.config
        requested = {
            key: arguments[key]
            for key in ("horizon_cycles", "min_detection_fraction", "max_early_alarm_burden")
            if key in arguments
        }
        command = "python scripts/run_pipeline.py"
        if "horizon_cycles" in requested and requested["horizon_cycles"] != config.get("horizon_cycles"):
            command = (
                "python scripts/run_pipeline.py  # then set horizon_cycles in "
                "backend/app/config.py, which changes the configuration fingerprint"
            )
        if "min_detection_fraction" in requested:
            command += f" --min-detection {requested['min_detection_fraction']}"
        if "max_early_alarm_burden" in requested:
            command += f" --max-burden {requested['max_early_alarm_burden']}"

        return {
            "started": False,
            "reason": (
                "Training runs locally, not inside a conversation. The hosted service "
                "serves recorded evidence and has neither the memory nor the time "
                "budget to train."
                if not self.allow_training
                else "Training is available in this deployment but is not started by the copilot."
            ),
            "command": command,
            "requested_settings": requested,
            "current_settings": {
                "horizon_cycles": config.get("horizon_cycles"),
                "feature_window": config.get("feature_window"),
                "holdout_engines": config.get("holdout_engines"),
                "n_folds": config.get("n_folds"),
                "min_useful_lead": config.get("min_useful_lead"),
                "alert_rule": (
                    f"opens after {config.get('alert_on_consecutive')} consecutive scores "
                    f"at or above the threshold, closes after {config.get('alert_off_consecutive')} below"
                ),
            },
            "candidates": [
                {"candidate": c.candidate.value, "config_id": c.config_id, "description": c.description}
                for c in self.bundle.candidates
            ],
            "config_fingerprint": self.bundle.config_fingerprint,
        }

    def _run_fault_tests(self, arguments: dict[str, Any]) -> dict[str, Any]:
        required_only = arguments.get("required_only", True)
        wanted = arguments.get("candidate")

        results = [
            r
            for r in self.bundle.scenario_results
            if r.scenario_id != CLEAN_SCENARIO_ID
            and (not required_only or r.required)
            and (wanted is None or r.candidate.value == wanted)
        ]
        if not results:
            return {
                "scenarios": 0,
                "note": (
                    "No fault scenarios match that request. "
                    f"Candidates present: {sorted({r.candidate.value for r in self.bundle.scenario_results})}."
                ),
            }

        per_candidate: dict[str, dict[str, Any]] = {}
        for result in results:
            key = f"{result.candidate.value}/{result.config_id}"
            entry = per_candidate.setdefault(
                key, {"detections": [], "worst": None, "worst_scenario": None, "run_ids": []}
            )
            entry["detections"].append(result.metrics.detection_fraction)
            if entry["worst"] is None or result.metrics.detection_fraction < entry["worst"]:
                entry["worst"] = result.metrics.detection_fraction
                entry["worst_scenario"] = result.scenario_id
                entry["worst_label"] = result.fault.label() if result.fault else result.scenario_id
            if result.run_id:
                entry["run_ids"].append(result.run_id)

        clean_by_candidate = {
            f"{r.candidate.value}/{r.config_id}": r.metrics.detection_fraction
            for r in self.bundle.scenario_results
            if r.scenario_id == CLEAN_SCENARIO_ID
        }

        return {
            "scenarios": len(results),
            "required_only": bool(required_only),
            "fault_kinds": sorted({r.fault.kind.value for r in results if r.fault}),
            "sensors_tested": sorted({r.fault.sensor for r in results if r.fault}),
            "per_candidate": {
                key: {
                    "clean_detection_fraction": clean_by_candidate.get(key),
                    "mean_detection_fraction": sum(entry["detections"]) / len(entry["detections"]),
                    "worst_detection_fraction": entry["worst"],
                    "worst_scenario_id": entry["worst_scenario"],
                    "worst_case": entry.get("worst_label"),
                    "scenarios": len(entry["detections"]),
                }
                for key, entry in sorted(per_candidate.items())
            },
        }

    def _query_runs(self, arguments: dict[str, Any]) -> dict[str, Any]:
        wanted_candidate = arguments.get("candidate")
        wanted_scenario = arguments.get("scenario_id")
        wanted_metric = arguments.get("metric")
        limit = int(arguments.get("limit", 20))

        rows: list[dict[str, Any]] = []
        for result in self.bundle.scenario_results:
            key = f"{result.candidate.value}/{result.config_id}"
            if wanted_candidate and wanted_candidate not in ("all", result.candidate.value, key):
                continue
            if wanted_scenario and result.scenario_id != wanted_scenario:
                continue
            metrics = {
                "detection_fraction": result.metrics.detection_fraction,
                "detection_ci_lower": result.metrics.detection_ci.lower,
                "detection_ci_upper": result.metrics.detection_ci.upper,
                "early_alarm_burden": result.metrics.early_alarm_burden,
                "median_lead_time": result.metrics.median_lead_time,
                "engines": result.metrics.engines,
                "detected": result.metrics.detected,
                "late": result.metrics.late,
                "missed": result.metrics.missed,
                "new_episodes_per_1000": result.metrics.new_episodes_per_1000,
            }
            if wanted_metric:
                if wanted_metric not in metrics:
                    raise ToolError(
                        f"unknown metric {wanted_metric!r}; available: {sorted(metrics)}"
                    )
                metrics = {wanted_metric: metrics[wanted_metric]}
            rows.append(
                {
                    "candidate": key,
                    "scenario_id": result.scenario_id,
                    "required": result.required,
                    "partition": result.partition.value,
                    "threshold": result.threshold,
                    "metrics": metrics,
                    "run_id": result.run_id,
                }
            )
            if len(rows) >= limit:
                break

        if not rows:
            return {
                "results": [],
                "note": (
                    "Nothing recorded matches that request. Scenario identifiers look "
                    "like 'dropout-persistent-sensor_2-on60', and 'clean' means the "
                    "unfaulted result."
                ),
            }
        return {
            "results": rows,
            "truncated": len(rows) >= limit,
            "config_fingerprint": self.bundle.config_fingerprint,
            "data_hash": self.bundle.profile.data_hash,
        }

    def _draft_report(self, arguments: dict[str, Any]) -> dict[str, Any]:
        selection = self.bundle.development_selection
        return {
            "outcome": selection.outcome.value,
            "criteria": selection.criteria.model_dump(mode="json"),
            "recommended": (
                {
                    "candidate": selection.recommended.candidate.value,
                    "config_id": selection.recommended.config_id,
                    "threshold": selection.recommended.threshold,
                    "clean_detection_fraction": selection.recommended.clean.detection_fraction,
                    "clean_detection_ci": selection.recommended.clean.detection_ci.model_dump(mode="json"),
                    "clean_early_alarm_burden": selection.recommended.clean.early_alarm_burden,
                    "median_lead_time": selection.recommended.clean.median_lead_time,
                    "worst_required_detection": selection.recommended.worst_detection_required,
                    "worst_required_scenario": selection.recommended.worst_scenario_id,
                }
                if selection.recommended
                else None
            ),
            "ranking": [
                {
                    "candidate": v.candidate.value,
                    "config_id": v.config_id,
                    "qualifies": v.qualifies,
                    "clean_detection_fraction": v.clean.detection_fraction,
                    "mean_detection_required": v.mean_detection_required,
                    "worst_detection_required": v.worst_detection_required,
                    "notes": v.notes,
                }
                for v in selection.ranked
            ],
            "partitions": {
                "holdout_engines": len(self.bundle.splits.holdout),
                "development_engines": len(self.bundle.splits.development),
                "folds": len(self.bundle.splits.folds),
                "split_seed": self.bundle.splits.seed,
            },
            "calibration": [
                {"candidate": c.candidate.value, "config_id": c.config_id, "brier": c.brier}
                for c in self.bundle.calibration
            ],
            "uncertain_comparisons": selection.uncertain_comparisons,
            "notes": selection.notes,
            "limitations": self.bundle.limitations,
            "config_fingerprint": self.bundle.config_fingerprint,
            "git_commit": self.bundle.git_commit,
            "final_evaluation_run": self.bundle.final_evaluation is not None,
        }
