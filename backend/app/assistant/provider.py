"""Optional AI interpretation; the provider cannot write evidence, numbers, links or verdicts."""

import json
import re

from openai import AsyncOpenAI
from pydantic import Field

from app.assistant.evidence import with_brief
from app.assistant.schemas import AnalysisRequest, AnalysisResult
from app.schemas import Strict

ALIAS = re.compile(r"\b(model|case)-(\d+)\b", re.IGNORECASE)
LINK = re.compile(r"https?:|www\.|\]\(|\b[a-z0-9-]+\.(com|net|org|io|dev|ai|invalid)\b", re.IGNORECASE)
CLAIM = re.compile(r"\b(deploy\w*|approv\w*|root[- ]cause|caused?|causes|causation|physical\w*|guarantee\w*|certif\w*|percent\w*)\b", re.IGNORECASE)
NEGATIVE = re.compile(r"\bfail\w*|\bnot (meet|qualify|pass)\w*|n't (meet|qualify|pass)\w*|\bshort of\b", re.IGNORECASE)
POSITIVE = re.compile(r"\b(pass(es|ed|ing)?|qualif(y|ies|ied|ying)|meets?|met)\b", re.IGNORECASE)
MAX_INTERPRETATION = 600


class AnalysisChoices(Strict):
    finding_ids: list[str] = Field(min_length=1, max_length=3)
    action_id: str | None
    interpretation: str


def aliases(result: AnalysisResult, context: AnalysisRequest):
    candidate_alias = {name: f"model-{i + 1}" for i, name in enumerate(context.candidates)}
    scenario_alias = {}
    for ref in result.sources:
        if ref.scenario_id is not None:
            scenario_alias.setdefault(ref.scenario_id, f"case-{len(scenario_alias) + 1}")
    return candidate_alias, scenario_alias


def provider_packet(result: AnalysisResult, context: AnalysisRequest) -> dict:
    """Only server-generated categories and values leave the machine."""
    candidate_alias, scenario_alias = aliases(result, context)
    refs = {}
    for ref in result.sources:
        if ref.candidate not in candidate_alias or ref.partition != context.partition:
            raise ValueError("Evidence context mismatch.")
        refs[ref.id] = {"model": candidate_alias[ref.candidate], "case": scenario_alias.get(ref.scenario_id),
                        "metric": ref.metric, "value": ref.value, "unit": ref.unit}
    # No labels, identifiers, URLs, free-text limitations or raw sensor values.
    return {"task": context.task, "findings": [
        {"id": f.id, "tone": f.tone, "evidence": [refs[s] for s in f.source_ids]}
        for f in result.findings], "actions": [a.id for a in result.actions]}


def verify_interpretation(text: str, result: AnalysisResult, context: AnalysisRequest) -> str | None:
    """Reject numbers, links, unsupported claims and verdicts that contradict recorded qualification."""
    text = " ".join(text.split())
    if not text:
        return None
    if len(text) > MAX_INTERPRETATION:
        raise ValueError("Cloud interpretation is too long.")
    candidate_alias, scenario_alias = aliases(result, context)
    known = {alias.lower() for alias in [*candidate_alias.values(), *scenario_alias.values()]}
    if any(match.group(0).lower() not in known for match in ALIAS.finditer(text)):
        raise ValueError("Cloud interpretation referenced an unavailable model or case.")
    if re.search(r"\d", ALIAS.sub("", text)):
        raise ValueError("Cloud interpretation contained an unsupported numeric claim.")
    if LINK.search(text) or CLAIM.search(text):
        raise ValueError("Cloud interpretation contained an unsupported claim or link.")
    qualifies = {candidate_alias[s.candidate]: s.value == "True" for s in result.sources if s.metric == "qualifies"}
    for sentence in re.split(r"[.!?;]+", text):
        negative = bool(NEGATIVE.search(sentence))
        positive = bool(POSITIVE.search(NEGATIVE.sub("", sentence)))
        if not (negative or positive):
            continue
        mentioned = {m.group(0).lower() for m in ALIAS.finditer(sentence) if m.group(1).lower() == "model"}
        models = mentioned or set(qualifies)
        verdicts = {qualifies.get(alias) for alias in models}
        if len(verdicts) != 1 or (negative and positive) or None in verdicts:
            raise ValueError("Cloud interpretation stated an ambiguous verdict.")
        if verdicts.pop() != positive:
            raise ValueError("Cloud interpretation contradicted the recorded qualification.")
    return text


def render_aliases(text: str, result: AnalysisResult, context: AnalysisRequest) -> str:
    candidate_alias, scenario_alias = aliases(result, context)
    labels = {}
    for source in result.sources:
        parts = source.context.split(" · ")
        labels[candidate_alias[source.candidate]] = parts[0]
        if source.scenario_id is not None and len(parts) > 2:
            labels[scenario_alias[source.scenario_id]] = parts[2]
    return ALIAS.sub(lambda m: labels.get(m.group(0).lower(), m.group(0)), text)


async def enhance_analysis(result: AnalysisResult, context: AnalysisRequest, settings) -> AnalysisResult:
    packet = json.dumps(provider_packet(result, context), separators=(",", ":"))
    instruction = ("You help an engineer investigate recorded predictive-maintenance model tests. "
                   "Select up to three existing finding IDs, prioritizing failures and missing evidence, and one available action ID or null. "
                   "Then write an interpretation of at most three short sentences explaining what the selected findings mean together and why the action is a useful next check. "
                   "Refer to models and cases only by their aliases, such as model-1 or case-2. "
                   "Never write digits, quantities, links, deployment advice or physical failure causes; the application renders all numbers. "
                   "Simulated sensor faults describe model behavior, not equipment physics. "
                   "Never contradict the recorded qualification value. Do not invent identifiers.")
    # UTF-8 bytes conservatively bound ordinary tokenizer input, including schema overhead.
    schema_size = len(json.dumps(AnalysisChoices.model_json_schema()).encode())
    if len(packet.encode()) + len(instruction.encode()) + schema_size + 512 > 8000:
        raise ValueError("Evidence exceeds the cloud analysis input budget.")
    try:
        async with AsyncOpenAI(api_key=settings.openai_api_key, max_retries=0, timeout=40) as client:
            response = await client.responses.parse(
                model=settings.assistant_model, store=False, max_output_tokens=1200,
                input=[{"role": "system", "content": instruction}, {"role": "user", "content": packet}],
                text_format=AnalysisChoices)
    except Exception:
        raise RuntimeError("Cloud analysis is unavailable. Recorded evidence is still available.") from None
    choices = response.output_parsed
    if not isinstance(choices, AnalysisChoices):
        raise ValueError("Cloud analysis did not return a supported result.")
    by_id = {f.id: f for f in result.findings}
    if len(set(choices.finding_ids)) != len(choices.finding_ids) or any(i not in by_id for i in choices.finding_ids):
        raise ValueError("Cloud analysis referenced unavailable evidence.")
    if choices.action_id is not None and choices.action_id not in {a.id for a in result.actions}:
        raise ValueError("Cloud analysis referenced an unavailable action.")
    interpretation = verify_interpretation(choices.interpretation, result, context)
    ranked = [by_id[i] for i in choices.finding_ids] + [f for f in result.findings if f.id not in choices.finding_ids]
    actions = sorted(result.actions, key=lambda a: a.id != choices.action_id)
    enhanced = result.model_copy(update={
        "findings": ranked, "actions": actions, "mode": "ai", "model": settings.assistant_model,
        "interpretation": render_aliases(interpretation, result, context) if interpretation else None,
        "verification": "AI interpretation passed reference, number, link and verdict checks; all values come from recorded evidence"})
    return with_brief(enhanced, context)
