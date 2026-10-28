"""Provider transport only. Tool authority and evidence verification stay with callers."""
from dataclasses import asdict, dataclass

from pydantic import BaseModel

from app.config import validate_nebius_url


def provider_name(settings) -> str:
    value = getattr(settings, "assistant_provider", "openai")
    if value not in {"openai", "nebius"}:
        raise ValueError("Unsupported assistant provider")
    return value


def provider_label(settings) -> str:
    return "Nebius Token Factory" if provider_name(settings) == "nebius" else "OpenAI"


def key_variable(settings) -> str:
    return "NEBIUS_API_KEY" if provider_name(settings) == "nebius" else "OPENAI_API_KEY"


def api_key(settings) -> str:
    field = "nebius_api_key" if provider_name(settings) == "nebius" else "openai_api_key"
    return getattr(settings, field, "")


def provider_identity(settings) -> str:
    if provider_name(settings) == "nebius":
        return "nebius:" + validate_nebius_url(settings.nebius_base_url)
    return "openai"


def client_options(settings) -> dict:
    if not api_key(settings):
        raise ValueError(f"Configure {key_variable(settings)} on the server")
    options = {"api_key": api_key(settings), "max_retries": 0,
        "timeout": min(40, getattr(settings, "assistant_timeout_seconds", 45))}
    if provider_name(settings) == "nebius":
        options["base_url"] = validate_nebius_url(settings.nebius_base_url)
    return options


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: str
    type: str = "function_call"

    def model_dump(self, **_kwargs):
        return asdict(self)


def chat_messages(history: list[dict]) -> list[dict]:
    """Convert our private, provider-independent tool transcript to chat messages."""
    messages: list[dict] = []
    for item in history:
        if item.get("type") == "function_call":
            call = {"id": item["call_id"], "type": "function",
                "function": {"name": item["name"], "arguments": item["arguments"]}}
            if messages and messages[-1].get("tool_calls"):
                messages[-1]["tool_calls"].append(call)
            else:
                messages.append({"role": "assistant", "tool_calls": [call]})
        elif item.get("type") == "function_call_output":
            messages.append({"role": "tool", "tool_call_id": item["call_id"], "content": item["output"]})
        elif item.get("role") in {"system", "user", "assistant"} and isinstance(item.get("content"), str):
            messages.append({"role": item["role"], "content": item["content"]})
        else:
            raise ValueError("Unsupported investigation transcript entry")
    return messages


def strict_schema(model: type[BaseModel]) -> dict:
    """Require explicit properties without changing the server's validation model."""
    def visit(value):
        if isinstance(value, list):
            return [visit(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {key: ({name: visit(schema) for name, schema in item.items()}
            if key in {"properties", "$defs", "patternProperties"} else visit(item))
            for key, item in value.items() if key != "default"}
        if result.get("type") == "object" and "properties" in result:
            result["additionalProperties"] = False
            result["required"] = list(result["properties"])
        return result
    return visit(model.model_json_schema())


def nebius_options(settings, max_output_tokens: int) -> dict:
    """Allow reasoning tokens within the total completion limit."""
    effort = getattr(settings, "nebius_reasoning_effort", "low")
    headroom = 0 if effort == "none" else getattr(settings, "nebius_reasoning_tokens", 4096)
    return {"max_tokens": max_output_tokens + headroom, "reasoning_effort": effort}


def visible_content(content: str) -> str:
    """Drop a leading reasoning block when an endpoint returns it inline."""
    text = content.lstrip()
    if text.startswith("<think>"):
        end = text.find("</think>")
        if end < 0:
            raise ValueError("Provider returned unfinished reasoning instead of an answer")
        text = text[end + len("</think>"):]
    return text.strip()


def complete_message(response, *, tools=False):
    if len(response.choices) != 1:
        raise ValueError("Provider returned an unsupported number of choices")
    choice = response.choices[0]
    if choice.finish_reason not in ({"stop", "tool_calls"} if tools else {"stop"}) or choice.message.refusal:
        raise ValueError("Provider response was incomplete or refused")
    return choice.message


async def request_structured(client, settings, *, history, response_model, max_output_tokens):
    if provider_name(settings) == "openai":
        response = await client.responses.parse(model=settings.assistant_model, store=False,
            max_output_tokens=max_output_tokens, input=history, text_format=response_model)
        return response.output_parsed
    response = await client.chat.completions.create(model=settings.assistant_model, messages=chat_messages(history),
        **nebius_options(settings, max_output_tokens), response_format={"type": "json_schema", "json_schema": {
            "name": response_model.__name__, "strict": True, "schema": strict_schema(response_model)}})
    message = complete_message(response)
    if message.tool_calls or not message.content or len(message.content.encode()) > 100_000:
        raise ValueError("Provider returned an unsupported structured response")
    content = visible_content(message.content)
    if not content:
        raise ValueError("Provider returned an unsupported structured response")
    return response_model.model_validate_json(content, strict=True)


async def request_tool_calls(client, settings, *, history, tools, forced, max_output_tokens):
    if provider_name(settings) == "openai":
        response = await client.responses.create(model=settings.assistant_model, store=False,
            max_output_tokens=max_output_tokens, input=history, tools=tools,
            tool_choice={"type": "function", "name": forced} if forced else "auto", parallel_tool_calls=False)
        return [item for item in response.output if item.type == "function_call"]
    response = await client.chat.completions.create(model=settings.assistant_model, messages=chat_messages(history),
        **nebius_options(settings, max_output_tokens), tools=[{"type": "function", "function": {
            key: value for key, value in spec.items() if key != "type"}} for spec in tools],
        tool_choice={"type": "function", "function": {"name": forced}} if forced else "auto", parallel_tool_calls=False)
    message = complete_message(response, tools=True)
    calls = message.tool_calls or []
    if len(calls) > 8 or any(call.type != "function" or not call.id or not call.function.name
            or not isinstance(call.function.arguments, str) or len(call.function.arguments.encode()) > 2048 for call in calls):
        raise ValueError("Invalid investigation tool call")
    if forced and (len(calls) != 1 or calls[0].function.name != forced):
        raise ValueError("Provider did not perform the required evidence inspection")
    return [ToolCall(call.id, call.function.name, call.function.arguments) for call in calls]
