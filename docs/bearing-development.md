# Bearing development checks — 2026-10-31

These later development experiments use measured XJTU-SY laboratory recordings. They do not establish field performance or update the original submitted source archive. All fifteen bearing histories were already exposed; the new studies use the same twelve development bearings and do not reread the three previously reserved signals.

The fixed limits remain 80% useful warnings and 5% early alarm burden. Windows use acquisition minutes: 30-minute horizon, ten-minute useful lead, five-minute late window, 45-minute transition boundary, five-recording trailing features and two-reading alert persistence. Operating requirements remain provisional pending a real engineer review. One development history has no eligible early-life alarm window; it cannot count as zero alarms.

## Fixed feature comparison

The predetermined rich pack adds kurtosis, crest factor, peak-to-peak amplitude and three broad spectral energies to each axis's RMS. A nested grouped development comparison kept the same model parameters and operating windows:

| Input/model | Useful warnings | Pooled alarms | Worst machine |
|---|---:|---:|---:|
| RMS / logistic regression | 9/12 | 2.82% | 52.25% |
| Rich / logistic regression | 7/12 | 35.88% | 99.51% |
| RMS / XGBoost | 5/12 | 1.33% | 17.60% |
| Rich / XGBoost | 7/12 | 21.53% | 60.06% |

Every strict per-machine inner selection failed the warning requirement. No outer group was admitted under that procedure, so its outer metrics remain unavailable. Richer features did not provide an accepted remedy.

## Raw measurement faults

A separate diagnostic trained fixed grouped development models and used a declared 0.5 cutoff. These numbers use a different procedure from the nested table above:

| Input/model | Clean useful warnings | Pooled alarms | Worst machine |
|---|---:|---:|---:|
| RMS / logistic regression | 10/12 | 4.80% | 51.35% |
| Rich / logistic regression | 11/12 | 9.88% | 89.04% |
| RMS / XGBoost | 7/12 | 1.49% | 17.39% |
| Rich / XGBoost | 6/12 | 3.09% | 24.43% |

Eight fixed measurement faults per arm act on original accelerometer samples before all derived and trailing features are rebuilt. Dropout marks the whole axis missing; stuck holds the prior burst's final sample; additive drift uses raw-sample variation from training groups only. These represent whole acquired bursts, not mechanical damage or behavior between acquisitions. Startup-relative inputs and partial-burst corruption are unsupported.

All 32 fault findings are inconclusive under the per-machine criterion. No model or threshold was promoted. Exact cutoff searches remain read-only diagnostics; they never replace a rejected cutoff with an accepted-looking fallback. Current investigation views expose the pooled, equal-machine mean and worst burden, individual warning outcomes, denominators, missing windows and explicit no-qualifying-cutoff states.

[Aggregate evidence](../evidence/development/bearing-vibration-20261031.json) records the procedures, source fingerprints and verification. Frozen full manifests and matching source snapshots remain local study artifacts. Replaying source-bound contexts requires those matching sources and dependencies; current code does not silently reuse older contexts. No new paid requests, engineer participation or genuinely fresh equipment validation occurred in these two studies.
