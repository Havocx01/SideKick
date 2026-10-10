# Back up and recover Sidekick

GitHub backs up the application code. This tool backs up the separate local workspace: uploaded CSVs and mappings, run artifacts and frozen models, experiment folders and labels, analysis and review drafts, pilot records, consent/provenance/revocation metadata and the reserved-history exposure ledger. It also includes the configured recorded benchmark bundle. Evidence bytes and identifiers are preserved.

## Create and verify a backup

Stop Sidekick with Ctrl+C in its server window first. Finish or cancel any training or analysis before stopping. The backup refuses an active server or active job; it does not stop processes or cancel work for you. If a crash left an active record, start and stop Sidekick normally so its existing recovery marks interrupted work.

From the project folder in PowerShell:

```powershell
.\tasks.ps1 backup
```

The command loads `.env` settings for `SIDEKICK_DATA_DIR`, `SIDEKICK_ARTIFACTS_DIR` and `SIDEKICK_BUNDLE_PATH`, with existing environment variables taking precedence. It uses SQLite's backup API, including committed WAL data, holds the workspace/server and database write locks, checks for changing files, and verifies every archived checksum before publishing the ZIP. Default output is a timestamped file in `output/backups`.

Choose a different destination and verify it later:

```powershell
.\tasks.ps1 backup -OutputPath 'D:\Sidekick backups\pilot.zip'
.\tasks.ps1 verify-backup -Archive 'D:\Sidekick backups\pilot.zip'
```

Copy the ZIP to storage separate from this computer. The tool does not upload or schedule backups. The ZIP contains private equipment data and edited briefs; it is not encrypted. Store it with the same access restrictions as the workspace. Environment files, common private-key files, logs, lock files and caches are excluded; it does not scan CSV contents for secrets.

## Recover into a new workspace

Only restore a backup you created and trust. Checksums detect damage; they do not authenticate a backup's author. Frozen model files are copied without deserializing them, but a later validation operation can load those models.

```powershell
.\tasks.ps1 restore -Archive 'D:\Sidekick backups\pilot.zip' -Destination 'D:\Sidekick recovered'
```

The destination must not already exist. Recovery verifies names, sizes, checksums and SQLite integrity before publishing the new workspace. It never merges into or overwrites the original. A failed recovery cleans up its own temporary workspace.

Start the recovered workspace from the same project and a compatible Python/training dependency installation:

```powershell
$env:SIDEKICK_MODE = 'full'
$env:SIDEKICK_DATA_DIR = 'D:\Sidekick recovered\data'
$env:SIDEKICK_ARTIFACTS_DIR = 'D:\Sidekick recovered\artifacts'
$env:SIDEKICK_BUNDLE_PATH = 'D:\Sidekick recovered\evidence\bundle.json'
.\tasks.ps1 api
```

Do not launch a second workspace on the original server port. Stop the original server first. Configure API credentials separately; none are included in the backup. To return to the original workspace, stop the recovered server and remove these three path variables (or restore your previous values).

`backup-manifest.json` records file hashes, snapshot date, application commit, Python and training package versions. It records the installed commit, so uncommitted code changes are not represented by that commit. Model/source compatibility checks remain enforced; recovery does not approve new scoring or reset any exposure history.

## Access and retention

Analysis ownership is retained exactly. A saved analysis may require the original browser's owner cookie; the backup does not transfer browser cookies, log you in, or make another owner's answers accessible. Revoked drafts remain revoked, and public-record expiry still applies. This command is for local full mode, not a way to keep a hosted visitor session alive.

A backup is a point-in-time snapshot. Later edits, revocations and exposure events are absent from older ZIPs. Never treat histories exposed after that snapshot as fresh by switching to an old workspace. Restore for recovery, retain any newer audit records, and obtain genuinely fresh histories for any new independent check. If you revoke/delete private interpretations, remove older backups containing them according to your own retention policy.

The original data and artifacts directories must be separate, without links/junctions inside them. Empty directories, MLflow's separate `mlruns` convenience mirror, application code, frontend build and browser state are outside this backup. File count and expanded size are bounded at 200,000 files and 100 GiB. Backups never launch training, AI analysis or reserved validation.

For macOS/Linux or explicit paths, use the same Python CLI:

```sh
.venv/bin/python scripts/workspace_backup.py create --output /safe/place/pilot.zip
.venv/bin/python scripts/workspace_backup.py verify /safe/place/pilot.zip
.venv/bin/python scripts/workspace_backup.py restore /safe/place/pilot.zip --destination /new/workspace
```
