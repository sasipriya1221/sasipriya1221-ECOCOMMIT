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

The current offline core passes **50/50 tests** in GitHub Actions (Offline Regression run `33428221026`, head `43f93cc61724ca2beb54f361b9553968168476b7`). Provider access is no longer blocked by the earlier OpenAI credit issue: the project uses the configured Groq OpenAI-compatible endpoint with `openai/gpt-oss-120b` and the repository secret is injected only through GitHub Actions.

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

The retained artifact from that failed run shows concrete failure classes: contract validation/source-span errors, missing negation/exception/dependency structure, uncovered numeric signals, and ambiguity handling that sometimes validated or rejected when clarification was required. Those results remain failed development evidence; they are not relabeled or discarded.

A later 10-clear + 10-ambiguous real-model development smoke (GitHub Actions run `33426475689`, head `45f4c0158d3917e3174741217f9a90bf5f496a6f`) completed and also remains failed intermediate evidence:

- passed cases: 3 / 20
- case pass rate: 15.00%
- autonomous coverage: 10.00%
- selective semantic reliability: 100.00% among the two autonomously validated cases
- ambiguous clarification accuracy: 10.00%
- 16 / 20 cases failed with Groq HTTP 429 token-per-day exhaustion rather than a semantic result
- one parsed ambiguous case (`A008`) was incorrectly rejected because the deterministic negation guard treated the vague phrase `not too much` as a prohibition; that validator defect is now fixed with regressions

Because 16/20 cases had no usable model result, this smoke cannot be interpreted as a semantic estimate and cannot pass Checkpoint A.

## Corrections now on `main`

Implementation changes are constrained to justified M2/M3 defects and provider reliability; the frozen gate is unchanged:

- exact source-span offset repair and case-preserving grounding;
- deterministic `EXPLICIT_USER` provenance repair only when an exact source span proves it, with an explicit regression that ungrounded clauses receive no such repair;
- word-boundary dependency detection so text such as `certified` cannot create a fake `if` condition;
- clarification-class handling for material inference, unresolved dependency structure, and economically material open-textured language;
- supplier-selection vagueness coverage for terms such as `good`, `trustworthy`, `reputable`, and `clearly better`;
- corrected negation classification so `not too much` is vagueness while genuine `not recurring` authority remains a strict negation requirement;
- certified-product composition matching in the benchmark scorer without changing expected outcomes;
- compact failure diagnostics in both smoke and full workflows;
- low reasoning effort for this structured extraction workload;
- provider retries for HTTP 429/5xx and transient transport failures, respecting long `Retry-After` windows with a bounded ceiling;
- Groq JSON Schema structured outputs enabled for the live workflows so required contract fields are provider-constrained rather than repaired by guesswork;
- a 2,048-token completion ceiling to bound free-tier token consumption while leaving room for multi-clause contracts;
- serialized live requests and CI concurrency/time bounds.

A one-request provider-contract preflight is running from the current implementation to verify that Groq accepts the strict schema and returns an ECOCOMMIT contract before spending another 20-case smoke budget. The next 20-case smoke must run from the current head; only after that development smoke is usable will a new full 50+30 real-model gate run be launched.

No M4 / Checkpoint B work begins until a subsequent **full 50+30 real-model run** meets every frozen Checkpoint A threshold in the same run.
