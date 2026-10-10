# Sidekick implementation plans

| Plan | Status | Priority | Effort | Notes |
|---|---|---|---|---|
| [GitHub failures and safe cleanup](2026-10-10-sidekick-ci-cleanup.md) | DONE | P1 | S | 246 backend / 68 browser / 7 protocol checks. Exact evidence bytes preserved; status assertion scoped; unused UI/dependency removed. Cache deletion blocked by host policy; caches retained. Single owner, no subagents. Uncommitted/unpushed; remote CI needs the fix pushed. Local Docker engine stopped; latest hosted-memory job passed. |
| [Backup, startup and engineer evaluation](2026-10-09-sidekick-next-improvements.md) | DONE | P2 | M | 242 offline backend / 67 browser / 7 protocol checks; Windows and Linux fixture recovery; 14.5% compressed startup reduction; 12-case reviewer pack. Subsequently committed in 45dbe08. No provider calls or actual training in that task. Engineer study still requires a participant. |
| [Reliability completion](2026-10-09-sidekick-reliability-completion.md) | DONE | P1 | L | Nine technical priorities resolved. Fresh deployment follow-up: 212 backend / 68 browser / 7 protocol checks; Docker builds, loopback, replay capacity/restart/expiry and hosted memory pass. Application committed in a807144; verification follow-up committed locally. No public deployment by this task. Engineer benefit remains unmeasured. |
| [Review remediation](2026-10-09-sidekick-review-remediation-plan.md) | DONE | P1 | L | F1–F14 and follow-up fixes verified; Docker prerequisite resolved by the deployment runtime receipt. Reviewed application and verification follow-up committed locally. Field reliability and engineer study remain separate. |

Last touched: 10 October 2026.
