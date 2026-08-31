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

The offline core passes 36/36 tests. Provider access is no longer blocked by the earlier OpenAI credit issue: the project now uses the configured Groq OpenAI-compatible endpoint with `openai/gpt-oss-120b`, and the Groq provider preflight has passed with the repository secret injected.

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

Those results are retained as failed development evidence; they are not relabeled or discarded. Subsequent changes fixed justified implementation defects including source-span offset repair, dependency/clarification handling, a compact intent contract prompt, and bounded provider retry delays, with regression tests added for the discovered failure classes.

A fresh 10-clear + 10-ambiguous real-model development smoke run has been triggered from the bounded-retry head (`45f4c0158d3917e3174741217f9a90bf5f496a6f`). Its offline regression and Groq-secret checks have passed; the live cases are still executing. This smoke run is diagnostic only and cannot itself mark Checkpoint A passed.

No M4 / Checkpoint B work begins until a subsequent **full 50+30 real-model run** meets every frozen Checkpoint A threshold in the same run.
