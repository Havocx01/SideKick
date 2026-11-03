# Private full workspace

The private hosting configuration runs uploads, training, investigations and saved results behind sign-in. Each deployment has one owner and one persistent workspace. Give additional owners separate deployments and volumes. The existing public demo uses its restricted `demo` mode.

This configuration is prepared for deployment. Local HTTPS and automated checks do not establish that a public server has been provisioned or verified. The public demo has not been switched to private full mode.

## Configure access

From the repository root, create a new environment file:

```powershell
.venv\Scripts\python.exe scripts/create_hosted_login.py --owner adam --origin https://workspace.example.com
```

Replace the origin with the actual workspace domain. Enter a password when prompted. The helper writes a salted PBKDF2 hash to `.env.hosted` and never prints the password. `--generate` instead saves a random password beside the environment file; move that password into your password manager. Existing files are preserved. Keep these files private and out of source archives. The generated files disable live AI and set paid daily allowances to zero.

An existing storage directory is bound to its configured owner. Changing the owner requires a separate workspace. Changing the password hash invalidates existing sessions without clearing saved data or usage counters. Sessions expire within eight hours; signing out revokes the current session.

## Deploy the prepared configuration

Use a server with Docker Compose, a domain pointed at that server, and inbound ports 80 and 443 available. Transfer the source and `.env.hosted` privately to it, then run:

```sh
node scripts/check_hosted_compose.mjs
docker compose --env-file .env.hosted -f compose.hosted.yaml up --build -d
```

The checker renders configuration without displaying credentials. Caddy manages HTTPS for the configured hostname and forwards requests to the private API. Its certificate storage and the application workspace use named volumes. See [Caddy HTTPS](https://caddyserver.com/docs/automatic-https) and [Docker Compose services](https://docs.docker.com/reference/compose-file/services/).

Only the proxy publishes ports. The API trusts forwarded headers inside this isolated Compose network; keep its port unpublished. A standalone API process should trust only its actual reverse proxy. See [Uvicorn proxy settings](https://uvicorn.dev/settings/).

The `hosted` image refuses to start without its owner, HTTPS origin and password hash. It runs as a non-root user with a read-only filesystem, a writable persistent workspace and bounded temporary storage. Compose caps application memory at 2 GiB, CPU at two cores and process count at 128. Ordinary Docker builds still produce the restricted public demo.

## AI allowances and consent

To enable paid actions, explicitly configure the server key, live flag and finite allowances in the private environment file, then recreate the application container:

```dotenv
SIDEKICK_ASSISTANT_LIVE_ENABLED=1
NEBIUS_API_KEY=
TAVILY_API_KEY=
SIDEKICK_HOSTED_MAX_CALLS=8
SIDEKICK_HOSTED_MAX_COMPLETION_TOKENS=32768
SIDEKICK_HOSTED_MAX_SEARCHES=4
```

Those numbers are example ceilings, not estimated prices. Keep zero allowances until you choose a budget. Each actual Nemotron request reserves one call and its full completion ceiling, including reasoning, before sending. Each Tavily search reserves one search. Failed or interrupted requests retain their reservations. Counts are atomic, persist across sessions and restarts, and reset by UTC date. All model features share this daily boundary; the existing per-action consent and investigation limits still apply. Setting a key alone starts no work.

Authenticated mutations also consume a daily admission allowance, default 200. Body sizes are bounded before handling; CSV admission retains its existing stricter 10 MiB limit. These are request/admission controls, not filesystem quotas or billing guarantees. Monitor host disk space and maintain backups.

## Saved work and verification

The workspace volume contains SQLite records, datasets, fitted contexts, job status and exported artifacts. Keep it when updating the image. Jobs use the existing single-worker lock, cancellation and bounded lifetime; interrupted jobs are recorded on recovery. Back up a stopped workspace and its owner configuration together. Follow the [backup guidance](workspace-backup.md), and retain proxy volumes for HTTPS certificate state.

Before calling a public deployment complete, verify its real HTTPS origin, sign-in/out, anonymous denial of private API/export routes, synthetic model preparation and saved investigation, restart persistence, zero unexpected provider calls, and an actual backup/restore. Container execution and public deployment are separate checks from configuration rendering. Raw vibration contexts still require their verified local source files; raw remote execution, raw augmentation and fresh raw validation from a feature CSV alone are deliberately unavailable.
