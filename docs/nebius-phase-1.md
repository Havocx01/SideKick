# Nebius Investigator: Phase 1

Phase 1 adds NVIDIA/Nebius inference support to Sidekick's existing read-only deep investigation. Fault experiments are discovered and executed by the Nemotron controller in [the investigation guide](nebius-phase-3.md). Training, metrics, validation, routine analysis and the recorded benchmark remain local and deterministic.

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

Reasoning can consume the completion allowance before the model answers. Sidekick sends `reasoning_effort` (default `low`) and adds `SIDEKICK_NEBIUS_REASONING_TOKENS` (default 4,096) to the base output allowance. The resulting `max_tokens` is a shared ceiling for reasoning and visible text, not a separate limit on either portion. Extra headroom reduces truncation risk but cannot guarantee an answer; truncated output is still rejected without retries. Set `SIDEKICK_NEBIUS_REASONING_EFFORT=none` to request reasoning off with no extra allowance. Supported controls depend on the selected model; confirm compatibility for your endpoint. See the [Token Factory request example](https://dev.nebius.com/cookbook/beam-reflection-token-factory) for effort controls and shared output accounting.

Nebius is the default and only live provider. `SIDEKICK_ASSISTANT_PROVIDER` can be omitted or set to `nebius`; other values are rejected. No OpenAI account or key is needed. The OpenAI SDK supplies compatible Chat Completions transport to the validated Nebius endpoint. Remove any old GPT model override; the default is `nvidia/nemotron-3-super-120b-a12b`. An explicitly configured model overrides that default. Shell variables take precedence over `.env`. The local `.env` is never edited by the configuration check.

## Check connectivity

From the repository root on Windows:

```powershell
.venv\Scripts\python.exe scripts/check_nebius.py
```

This only reports configuration and key availability; it makes no network requests and prints no key values.

Once a key is configured, the following explicitly permits two billable requests, with no retries and a total completion limit of 1,024 plus the configured reasoning reserve per request (5,120 with defaults). The offline report shows this total before any request:

```powershell
.venv\Scripts\python.exe scripts/check_nebius.py --live
```

Use `--model nvidia/<available-model-id>` to test a different NVIDIA model. The first request forces a read-only synthetic tool call; the second supplies its synthetic result and validates a strict structured response. No equipment data, uploaded files, saved analyses, training or reserved-evaluation histories are used. The process has a 45-second overall limit. Failed, refused, malformed or truncated responses fail the probe instead of triggering retries.

Passing this probe verifies basic connectivity and transport contracts for that endpoint/model. It does not establish deep-investigation quality, performance benefits or hackathon readiness.

The optional `scripts/evaluate_deep.py --live` evaluation also uses Nebius. Supply `--input-usd-per-million` and `--output-usd-per-million` with your model's current prices. The durable campaign records these rates and the model; changing them requires a new campaign. The cost reservation includes the shared reasoning/output allowance. Offline evaluation and replay of historical captures need no key or prices.

## What changed

- Nebius-only live configuration, validated endpoint and Nemotron default.
- Nebius Chat Completions transport for strict JSON and tool calling, retaining local evidence/citation validation.
- Provider-aware availability, sanitized error messages, consent disclosures and saved-output identities.
- Durable Nebius endpoint approval; workspace revocation clears all provider approvals. Old OpenAI approval does not authorize Nebius.
- Provider credentials, including any leftover OpenAI key in the parent environment, are removed from local training-worker environments.
- Synthetic connectivity checker and offline real-SDK transport/lifecycle regression coverage.

## Remaining submission work

Build compound-fault evaluation, the bounded adaptive investigator, reduction/replay artifacts, remedy/regression testing and fair search baselines. Confirm shared-code rights and add a root open-source license before public submission. Prepare a runnable judged build, a public video, technology feedback and a precise account of work completed during the submission period.

Reference: [Nebius structured output](https://docs.tokenfactory.nebius.com/ai-models-inference/json), [function calling](https://docs.tokenfactory.nebius.com/ai-models-inference/function-calling), and [official Nemotron Super example](https://github.com/nebius/token-factory-cookbook/blob/main/models/nemotron/nemotron3-super-120B.md).
