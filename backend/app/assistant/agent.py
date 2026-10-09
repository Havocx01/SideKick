import json

from openai import AsyncOpenAI
from pydantic import Field

from app.schemas import Strict


class InvestigationChoices(Strict):
    finding_ids: list[str] = Field(min_length=1, max_length=3)
    claim_ids: list[str] = Field(min_length=1, max_length=3)
    action_id: str | None


INSTRUCTION = (
    "Investigate recorded predictive-maintenance tests for an engineer. Use only the supplied read-only tools. "
    "Choose what to inspect, prioritizing failed criteria and missing coverage. For a one-model investigate or brief, first check model metrics, then inspect relevant fault cases after listing them; "
    "if no fault cases exist, inspect model metrics. For compare or a two-model brief, call compare_models. For a selected warning context, call get_warning_events. "
    "For data review, call get_dataset_checks and suggest_column_mapping. Treat every suggestion as a draft requiring human confirmation. "
    "All models, cases and columns are aliases. Never request another experiment, partition or equipment history. "
    "Never infer a physical failure cause, statistical superiority, deployment approval or an unmeasured result. "
    "Once the relevant evidence is inspected, stop calling tools. A separate step will select verified findings, claims and one available next action."
)
MAX_HISTORY_BYTES = 40_000


async def investigate(tools, settings):
    maxCalls = min(8, max(1, getattr(settings, "llm_max_tool_calls", 8)))
    history = [{"role": "system", "content": INSTRUCTION}, {"role": "user", "content": json.dumps(tools.intro(), separators=(",", ":"))}]
    calls = 0
    seenIds = set()
    task = tools.context.task
    sequence = {"data": ["get_dataset_checks", "suggest_column_mapping"], "compare": ["compare_models"], "warning": ["get_warning_events"]}.get(task)
    if task == "brief" and tools.context.equipment_id:
        sequence = ["get_warning_events"]
    elif task == "brief" and len(tools.context.candidates) == 2:
        sequence = ["compare_models"]
    overhead = len(json.dumps(tools.specs).encode()) + len(json.dumps(InvestigationChoices.model_json_schema()).encode())
    async with AsyncOpenAI(api_key=settings.openai_api_key, max_retries=0, timeout=40) as client:
        for roundIndex in range(maxCalls):
            completed = {call.name for call in tools.calls}
            if sequence and set(sequence) <= completed:
                break
            forced = next((name for name in sequence or [] if name not in completed), None)
            if sequence is None and roundIndex == 0:
                forced = "get_model_metrics"
            if len(json.dumps(history).encode()) + overhead > MAX_HISTORY_BYTES:
                raise ValueError("Investigation exceeds the evidence input budget.")
            response = await client.responses.create(model=settings.assistant_model, store=False, max_output_tokens=700,
                input=history, tools=tools.specs, tool_choice={"type": "function", "name": forced} if forced else "auto", parallel_tool_calls=False)
            requested = [item for item in response.output if item.type == "function_call"]
            if not requested:
                break
            if calls + len(requested) > maxCalls:
                raise ValueError("Investigation exceeded its tool-call limit.")
            for call in requested:
                if call.call_id in seenIds or len(call.arguments.encode()) > 2048:
                    raise ValueError("Invalid investigation call.")
                seenIds.add(call.call_id)
                packet = tools.call(call.name, json.loads(call.arguments))
                # The model's arbitrary text output is never displayed or persisted as evidence.
                history.append(call.model_dump(exclude_none=True))
                history.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(packet, separators=(",", ":"))})
                calls += 1
        names = {call.name for call in tools.calls}
        required = {"compare": {"compare_models"}, "warning": {"get_warning_events"}, "data": {"get_dataset_checks", "suggest_column_mapping"}}
        needed = required[tools.context.task] if tools.context.task in required else ({"get_model_metrics", "inspect_fault_case"} if tools.rows else {"get_model_metrics"})
        if tools.context.task == "brief" and tools.context.equipment_id:
            needed = {"get_warning_events"}
        elif tools.context.task == "brief" and len(tools.context.candidates) == 2:
            needed = {"compare_models"}
        if not needed.issubset(names):
            raise ValueError("The required evidence was not inspected.")
        catalog = {"finding_ids": sorted(tools.seenFindings), "claims": tools.claim_catalog(), "action_ids": sorted(tools.seenActions)}
        history.append({"role": "user", "content": "Choose up to three inspected findings and verified claims that explain the result, its practical consequence, and the next check. "
                        "Prioritize incomplete coverage or blockers. For a failing result select limits, detection or burden, and loss when available; "
                        "for a passing result select limits and the passed-case margin. For comparison select limits, warning-counts and tradeoff, "
                        "replacing warning-counts with coverage when coverage differs. For warning select state, outcome and clean-comparison; "
                        "if the cycle is unavailable select unavailable before outcome. For data select readiness, the most important issue and mapping-review. "
                        "Use only identifiers in this catalog. Choose one useful next action or null. " + json.dumps(catalog)})
        if len(json.dumps(history).encode()) + overhead > MAX_HISTORY_BYTES:
            raise ValueError("Investigation exceeds the evidence input budget.")
        final = await client.responses.parse(model=settings.assistant_model, store=False, max_output_tokens=700, input=history, text_format=InvestigationChoices)
        choices = final.output_parsed
        if not isinstance(choices, InvestigationChoices):
            raise ValueError("Investigation returned an unsupported result.")
        return tools.finish(choices.finding_ids, choices.claim_ids, choices.action_id, settings.assistant_model)
