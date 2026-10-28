"""Inspect Nebius configuration offline; --live permits exactly two synthetic requests."""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from openai import AsyncOpenAI

from app.assistant.transport import api_key, client_options, request_structured, request_tool_calls
from app.config import Settings
from app.schemas import Strict


class ProbeResult(Strict):
    status: Literal["ok"]
    count: Literal[1]


async def check_live(settings):
    """Use no files, equipment evidence, user records or application permission state."""
    history = [{"role": "system", "content": "Use the provided read-only synthetic probe tool."},
        {"role": "user", "content": "Call read_probe with probe_id synthetic-check."}]
    spec = {"type": "function", "name": "read_probe", "description": "Read a synthetic connectivity probe.",
        "parameters": {"type": "object", "properties": {"probe_id": {"type": "string", "enum": ["synthetic-check"]}},
            "required": ["probe_id"], "additionalProperties": False}, "strict": True}
    async with AsyncOpenAI(**client_options(settings)) as client:
        calls = await request_tool_calls(client, settings, history=history, tools=[spec], forced="read_probe", max_output_tokens=1024)
        if len(calls) != 1 or calls[0].name != "read_probe" or json.loads(calls[0].arguments) != {"probe_id": "synthetic-check"}:
            raise ValueError("The synthetic probe tool contract was not satisfied")
        history.extend([calls[0].model_dump(exclude_none=True), {"type": "function_call_output",
            "call_id": calls[0].call_id, "output": '{"status":"ok","count":1}'},
            {"role": "user", "content": "Return the probe result using the supplied JSON schema."}])
        await request_structured(client, settings, history=history, response_model=ProbeResult, max_output_tokens=1024)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Make two billable, synthetic-only requests; no retries.")
    parser.add_argument("--model", help="Explicit NVIDIA model ID available to this Nebius key.")
    args = parser.parse_args(argv)
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
    try:
        selected_model = args.model or (os.environ.get("SIDEKICK_ASSISTANT_MODEL", "")
            if os.environ.get("SIDEKICK_ASSISTANT_PROVIDER", "openai").strip().lower() == "nebius" else "")
        settings = Settings(assistant_provider="nebius", assistant_model=selected_model,
            assistant_timeout_seconds=20)
        if not settings.assistant_model.lower().startswith("nvidia/"):
            raise ValueError("Select an NVIDIA model with --model or SIDEKICK_ASSISTANT_MODEL")
    except ValueError:
        print("Invalid Nebius configuration. Check SIDEKICK_NEBIUS_BASE_URL and select an NVIDIA model.")
        return 2
    report = {"provider": "nebius", "endpoint": settings.nebius_base_url, "model": settings.assistant_model,
        "credential_configured": bool(api_key(settings)), "live_verified": False}
    if not args.live:
        report["note"] = "Offline inspection only. Use --live to test two synthetic requests with no retries."
        print(json.dumps(report, indent=2))
        return 0
    if not api_key(settings):
        print("Configure NEBIUS_API_KEY in the server environment or repository .env before using --live.")
        return 2
    try:
        asyncio.run(asyncio.wait_for(check_live(settings), timeout=45))
    except (ValueError, TimeoutError):
        print("Nebius probe failed or timed out. Tool calling and structured output have not been verified; no retries were made.")
        return 1
    except Exception as error:
        from app.assistant.service import provider_failure
        print(provider_failure(error, settings))
        return 1
    report.update(live_verified=True, requests=2, max_output_tokens_per_request=1024,
        note="Synthetic tool round-trip and structured response verified. Real investigation quality remains unmeasured.")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
