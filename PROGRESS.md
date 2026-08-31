# ECOCOMMIT Progress

| Milestone | Status | Acceptance gate |
|---|---|---|
| M0 Specification Freeze | 🟢 PASSED | Scope, hypothesis and metrics frozen in repo |
| M1 Economic Contract Language | 🟢 PASSED (offline acceptance) | 20 varied instructions fit one schema; authority invariant tested |
| M2 AI Intent Intelligence | 🟡 IN PROGRESS | Real Groq provider is connected; live semantic benchmark is being corrected against the frozen gate |
| M3 Fidelity + Abstention | 🟡 IN PROGRESS | Structural/ambiguity regressions pass offline; live ambiguity performance has not yet passed the frozen gate |
| M4 Policy Mapping | ⬜ NOT STARTED | Stop before Checkpoint B |

## Checkpoint A

**Status: 🔴 NOT PASSED YET**

The current offline core passes **43/43 tests** in GitHub Actions (Offline Regression run `33427260757`). Provider access is no longer blocked by the earlier OpenAI credit issue: the project now uses the configured Groq OpenAI-compatible endpoint with `openai/gpt-oss-120b`, and the Groq provider preflight has passed with the repository secret injected.

The Checkpoint A development stress set contains 80 cases: 50 clear compositional procurement instructions and 30 materially ambiguous instructions. Failed cases remain evidence; fixture/mock results do not count.

Frozen Checkpoint A gate (all required in the same real-model run):

- case pass rate >= 90%
- selective semantic reliability >= 95%
- autonomous coverage >= 55%
- ambiguous clarification accuracy >= 80%

## Live-run evidence

An earlier full Groq run (GitHub Actions run `33412737638`, head `37e78c93205e44c626b13e6bd694ca6c85d8c1ef`) completed against the real configured model and **failed** the frozen gate. Its aggregate metrics were:

- passed cases: 11 / 80
- case pass rate: 13.75%
- autonomous coverage: 30.00%
- selective semantic reliability: 41.67%
- ambiguous clarification accuracy: 13.33%

The retained artifact from that failed run shows concrete failure classes rather than a provider-credit problem: contract validation/source-span errors, missing negation/exception/dependency structure, uncovered numeric signals, and ambiguity handling that sometimes validated or rejected when clarification was required. Those results remain failed development evidence; they are not relabeled or discarded.

Subsequent implementation changes address those observed classes with regression coverage: exact source-span repair, word-boundary dependency detection, clarification-class handling for material inference and unresolved dependencies, explicit material-vagueness detection, certified-product composition matching, a compact intent contract prompt, compact failure diagnostics, bounded provider retries that respect `Retry-After`, transport-error retries, and configurable low reasoning effort for this structured extraction workload. The new provider-runtime regressions are included in the 43/43 passing offline suite.

A 10-clear + 10-ambiguous real-model development smoke run from earlier bounded-retry head `45f4c0158d3917e3174741217f9a90bf5f496a6f` is still executing. It does **not** include the newest low-reasoning/runtime-retry commits, so its artifact will be retained as intermediate evidence rather than treated as the final development result.

The current head is prepared for the next smoke with serialized Groq requests, low reasoning effort, CI concurrency guards/time bounds, and actionable artifact diagnostics. A smoke result can guide fixes but can never mark Checkpoint A passed.

No M4 / Checkpoint B work begins until a subsequent **full 50+30 real-model run** meets every frozen Checkpoint A threshold in the same run.
