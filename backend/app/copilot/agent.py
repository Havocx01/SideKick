"""The bounded copilot loop.

Three constraints shape this:

**Bounded.** A fixed tool-call budget, after which the loop stops and says so.
An agent that can loop indefinitely against a 512 MB service is a liability.

**Verified.** The draft answer's figures are checked against the tool results. On
a mismatch the model gets one chance to restate using only recorded values; if
figures are still unmatched they are flagged in the response rather than shown as
fact.

**Degradable.** With no API key, or if the provider fails, a deterministic
answer is produced directly from the evidence. The hosted demo therefore works
without a key, and the recorded video does not depend on a live API call.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from app.config import Settings, get_settings
from app.copilot.fallback import answer_without_llm
from app.copilot.tools import ToolError, ToolRegistry
from app.copilot.verify import annotate, correction_prompt, unverified, verify_answer
from app.schemas import CopilotAnswer, ToolInvocation
from app.utils.logging_setup import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """\
You are the Sidekick copilot. You help a maintenance engineer read the results of \
a completed model evaluation on sensor histories.

Rules you must follow:

1. You do not make predictions and you do not compute metrics. Predictions come \
from separate machine-learning models; metrics were computed by the evaluation \
pipeline and recorded. Your job is to look them up and explain them.
2. Every number you state must come from a tool result in this conversation. If \
you do not have a number, call a tool. If it was not measured, say so plainly.
3. Detection rates count equipment, not cycles. Quote the confidence interval \
whenever you quote a detection rate, because the evaluation holds out twenty \
engines and the intervals are wide.
4. If two candidates' intervals overlap, say the ordering is not established by \
the data rather than declaring a winner.
5. If no candidate met the criteria, report that as the result. Do not soften it \
and do not recommend the least bad option as though it qualified.
6. Distinguish a late warning from a missed one. A warning that arrives too late \
to act on is a different failure from no warning.
7. Be concise and concrete. Name the scenario that hurt a candidate most rather \
than describing robustness in the abstract.
8. This evaluation is on simulated aerospace data. Do not imply it validates \
behaviour on any specific plant equipment.
"""


@dataclass
class CopilotContext:
    registry: ToolRegistry
    settings: Settings


def ask(
    question: str,
    registry: ToolRegistry,
    *,
    settings: Settings | None = None,
) -> CopilotAnswer:
    """Answer one question, using tools, with figures verified."""
    settings = settings or get_settings()

    if not settings.llm_available:
        return answer_without_llm(question, registry, reason="no API key is configured")

    try:
        return _ask_with_llm(question, registry, settings)
    except Exception as exc:  # pragma: no cover - provider failures are environmental
        logger.warning("copilot call failed, answering from evidence instead: %s", exc)
        return answer_without_llm(
            question, registry, reason=f"the language model was unavailable ({type(exc).__name__})"
        )


def _ask_with_llm(question: str, registry: ToolRegistry, settings: Settings) -> CopilotAnswer:
    from openai import OpenAI

    client = OpenAI(api_key=settings.llm_api_key, timeout=settings.llm_timeout_s)

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    invocations: list[ToolInvocation] = []
    tool_payloads: list[object] = []
    truncated = False

    for _ in range(settings.llm_max_tool_calls):
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            tools=registry.schemas(),
            tool_choice="auto",
        )
        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))

        if not message.tool_calls:
            break

        for call in message.tool_calls:
            payload, invocation = _execute(registry, call.function.name, call.function.arguments)
            invocations.append(invocation)
            if invocation.ok:
                tool_payloads.append(payload)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(payload, default=str)[:20_000],
                }
            )
    else:
        truncated = True
        messages.append(
            {
                "role": "user",
                "content": (
                    "The tool-call budget is exhausted. Answer now with what you have, "
                    "and say which part of the question you could not check."
                ),
            }
        )
        response = client.chat.completions.create(
            model=settings.llm_model, messages=messages
        )
        message = response.choices[0].message

    text = (message.content or "").strip()
    claims = verify_answer(text, tool_payloads)

    if unverified(claims):
        # One chance to restate using only recorded values.
        messages.append({"role": "user", "content": correction_prompt(claims)})
        retry = client.chat.completions.create(model=settings.llm_model, messages=messages)
        retried = (retry.choices[0].message.content or "").strip()
        if retried:
            retry_claims = verify_answer(retried, tool_payloads)
            if len(unverified(retry_claims)) < len(unverified(claims)):
                text, claims = retried, retry_claims

    return CopilotAnswer(
        text=annotate(text, claims) if text else "No answer was produced.",
        tool_calls=invocations,
        citations=sorted({run_id for inv in invocations for run_id in inv.run_ids}),
        claims=claims,
        unverified_claims=len(unverified(claims)),
        truncated=truncated,
        degraded=False,
    )


def _execute(registry: ToolRegistry, name: str, raw_arguments: str) -> tuple[object, ToolInvocation]:
    started = time.perf_counter()
    try:
        arguments = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError as exc:
        return (
            {"error": f"arguments were not valid JSON: {exc}"},
            ToolInvocation(name=name, ok=False, error=str(exc)),
        )

    try:
        payload = registry.call(name, arguments)
    except ToolError as exc:
        return (
            {"error": str(exc)},
            ToolInvocation(name=name, arguments=arguments, ok=False, error=str(exc)),
        )
    except Exception as exc:  # pragma: no cover
        logger.exception("tool %s failed", name)
        return (
            {"error": f"{type(exc).__name__}: {exc}"},
            ToolInvocation(name=name, arguments=arguments, ok=False, error=str(exc)),
        )

    run_ids = _run_ids(payload)
    return payload, ToolInvocation(
        name=name,
        arguments=arguments,
        ok=True,
        duration_ms=(time.perf_counter() - started) * 1000.0,
        run_ids=run_ids,
    )


def _run_ids(payload: object, depth: int = 0) -> list[str]:
    """Collect run identifiers so an answer can cite its sources."""
    if depth > 6:
        return []
    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key == "run_id" and isinstance(value, str):
                found.append(value)
            elif key == "run_ids" and isinstance(value, list):
                found.extend(str(v) for v in value)
            else:
                found.extend(_run_ids(value, depth + 1))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(_run_ids(item, depth + 1))
    return found
