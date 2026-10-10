# Sidekick implementation plans

| Plan | Status | Priority | Effort | Notes |
|---|---|---|---|---|
| [Workspace AI permission](2026-10-10-workspace-ai-permission.md) | DONE | P1 | M | One approval for all local contexts; persistence and all-owner revocation. 251 offline backend / 38 browser / 7 protocol checks, lint/types/build pass. Hosted isolation and ownership retained. No paid requests or subagents; uncommitted and undeployed. |
| [Default motion and stable API startup](2026-10-10-motion-api-startup.md) | DONE | P1 | S | Animations default on; explicit off retained. Reload opt-in. 15 launcher/PowerShell checks, 30 affected browser checks across corrected-file runs, 7 protocol checks and build passed. No saved data edits, subagents, commit or deployment. |
| [GitHub failures and safe cleanup](2026-10-10-sidekick-ci-cleanup.md) | DONE | P1 | S | 246 backend / 68 browser / 7 protocol checks. Exact evidence bytes preserved; status assertion scoped; unused UI/dependency removed. Cache deletion blocked by host policy; caches retained. Single owner, no subagents. Uncommitted/unpushed; remote CI needs the fix pushed. Local Docker engine stopped; latest hosted-memory job passed. |
| [Backup, startup and engineer evaluation](2026-10-09-sidekick-next-improvements.md) | DONE | P2 | M | 242 offline backend / 67 browser / 7 protocol checks; Windows and Linux fixture recovery; 14.5% compressed startup reduction; 12-case reviewer pack. Subsequently committed in 45dbe08. No provider calls or actual training in that task. Engineer study still requires a participant. |
| [Reliability completion](2026-10-09-sidekick-reliability-completion.md) | DONE | P1 | L | Nine technical priorities resolved. Fresh deployment follow-up: 212 backend / 68 browser / 7 protocol checks; Docker builds, loopback, replay capacity/restart/expiry and hosted memory pass. Application committed in a807144; verification follow-up committed locally. No public deployment by this task. Engineer benefit remains unmeasured. |
| [Review remediation](2026-10-09-sidekick-review-remediation-plan.md) | DONE | P1 | L | F1–F14 and follow-up fixes verified; Docker prerequisite resolved by the deployment runtime receipt. Reviewed application and verification follow-up committed locally. Field reliability and engineer study remain separate. |

Last touched: 10 October 2026.
