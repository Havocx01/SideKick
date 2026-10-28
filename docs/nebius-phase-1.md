# Nebius Investigator: Phase 1

Phase 1 adds NVIDIA/Nebius inference support to Sidekick's existing read-only deep investigation. It does not yet discover or execute new fault experiments. Training, metrics, validation, routine analysis and the recorded benchmark remain local and deterministic.

## Configure

Put these settings in the server environment or the ignored repository `.env`:

```dotenv
SIDEKICK_ASSISTANT_PROVIDER=nebius
NEBIUS_API_KEY=your-server-side-key
SIDEKICK_NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1/
SIDEKICK_ASSISTANT_MODEL=nvidia/nemotron-3-super-120b-a12b
SIDEKICK_ASSISTANT_LIVE_ENABLED=1
```

Confirm the exact model ID, tool calling and JSON-schema support in your account's catalog. The model is a documented starting point, not a live-verified availability guarantee. A regional endpoint such as `https://api.tokenfactory.us-central1.nebius.com/v1/` can be selected explicitly. Only HTTPS Token Factory API endpoints are accepted; keys are never shared across providers.

Restart the API after changing configuration. Open **AI settings** and read the updated disclosure before enabling AI. Consent is scoped to the selected Nebius endpoint. Enabling it does not launch a request. Select a completed model result and explicitly start **Deep investigation**. Hosted demo and replay modes remain evidence-only for new work.

Existing OpenAI settings continue to work when the provider is `openai`, the compatibility default. An explicitly configured model overrides the provider's default: remove an old GPT model override when switching to Nebius. Shell variables take precedence over `.env`. The local `.env` is never edited by the configuration check.

## Check connectivity

From the repository root on Windows:

```powershell
.venv\Scripts\python.exe scripts/check_nebius.py
```

This only reports configuration and key availability; it makes no network requests and prints no key values.

Once a key is configured, the following explicitly permits two billable requests, with no retries and up to 1,024 output tokens per request:

```powershell
.venv\Scripts\python.exe scripts/check_nebius.py --live
```

Use `--model nvidia/<available-model-id>` to test a different NVIDIA model. The first request forces a read-only synthetic tool call; the second supplies its synthetic result and validates a strict structured response. No equipment data, uploaded files, saved analyses, training or reserved-evaluation histories are used. The process has a 45-second overall limit. Failed, refused, malformed or truncated responses fail the probe instead of triggering retries.

Passing this probe verifies basic connectivity and transport contracts for that endpoint/model. It does not establish deep-investigation quality, performance benefits or hackathon readiness.

## What changed

- Provider-specific configuration, isolated credentials, validated endpoint and Nemotron default.
- Nebius Chat Completions transport for strict JSON and tool calling, retaining local evidence/citation validation.
- Provider-aware availability, sanitized error messages, consent disclosures and saved-output identities.
- Durable Nebius endpoint approval; workspace revocation clears all provider approvals. Old OpenAI approval does not authorize Nebius.
- Both provider credentials are removed from local training-worker environments.
- Synthetic connectivity checker and offline real-SDK transport/lifecycle regression coverage.

## Remaining submission work

Build compound-fault evaluation, the bounded adaptive investigator, reduction/replay artifacts, remedy/regression testing and fair search baselines. Confirm shared-code rights and add a root open-source license before public submission. Prepare a runnable judged build, a public video, technology feedback and a precise account of work completed during the submission period.

Reference: [Nebius structured output](https://docs.tokenfactory.nebius.com/ai-models-inference/json), [function calling](https://docs.tokenfactory.nebius.com/ai-models-inference/function-calling), and [official Nemotron Super example](https://github.com/nebius/token-factory-cookbook/blob/main/models/nemotron/nemotron3-super-120B.md).
