import json
from types import SimpleNamespace


def chatCompletion(content=None, calls=None):
    message = SimpleNamespace(content=json.dumps(content) if content is not None else None, tool_calls=calls, refusal=None)
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason="tool_calls" if calls else "stop", message=message)])
