# ECOCOMMIT Progress

| Milestone | Status | Acceptance gate |
|---|---|---|
| M0 Specification Freeze | 🟢 PASSED | Scope, hypothesis and metrics frozen in repo |
| M1 Economic Contract Language | 🟢 PASSED (offline acceptance) | 20 varied instructions fit one schema; authority invariant tested |
| M2 AI Intent Intelligence | 🟡 IN PROGRESS | Real Groq provider is connected; latest Qwen development smoke is semantically clean; full frozen live gate is running |
| M3 Fidelity + Abstention | 🟡 IN PROGRESS | Structural/ambiguity regressions pass offline; latest Qwen smoke clarified all sampled ambiguous cases; full frozen live gate is running |
| M4 Policy Mapping | ⬜ NOT STARTED | Stop before Checkpoint B |

## Checkpoint A

**Status: 🟡 FULL FROZEN LIVE GATE RUNNING — NOT PASSED YET**

The current offline core passes **54/54 tests** in the latest Qwen development-smoke workflow. Provider access is through the configured Groq OpenAI-compatible endpoint with the repository secret injected only through GitHub Actions.

The frozen Checkpoint A benchmark contains 80 cases: 50 clear compositional procurement instructions and 30 materially ambiguous instructions. Failed cases remain evidence; fixture/mock results do not count.

Frozen Checkpoint A gate (all required in the same real-model full run):

- case pass rate >= 90%
- selective semantic reliability >= 95%
- autonomous coverage >= 55%
- ambiguous clarification accuracy >= 80%

## Live-run evidence retained

An earlier full Groq run (GitHub Actions run `33412737638`, head `37e78c93205e44c626b13e6bd694ca6c85d8c1ef`) completed against the real configured model and **failed** the frozen gate. Its aggregate metrics were:

- passed cases: 11 / 80
- case pass rate: 13.75%
- autonomous coverage: 30.00%
- selective semantic reliability: 41.67%
- ambiguous clarification accuracy: 13.33%

The retained artifact from that failed run shows concrete failure classes: contract validation/source-span errors, missing negation/exception/dependency structure, uncovered numeric signals, and ambiguity handling that sometimes validated or rejected when clarification was required. Those results remain failed development evidence; they are not relabeled or discarded.

A later 10-clear + 10-ambiguous real-model smoke (GitHub Actions run `33426475689`, head `45f4c0158d3917e3174741217f9a90bf5f496a6f`) also remained failed intermediate evidence because 16/20 cases hit Groq HTTP 429 token-per-day exhaustion and produced no usable model result.

The newest Qwen development smoke (GitHub Actions run `33430987810`, head `b398be64a22006d601d0686549aaf2183a78acfe`) completed successfully against `qwen/qwen3.8-27b` after the M2/M3 repairs:

- passed cases: 20 / 20
- case pass rate: 100.00%
- selective semantic reliability: 100.00%
- ambiguous clarification accuracy: 100.00%
- autonomous coverage: 50.00%
- failed cases: 0

The 50% autonomous-coverage value is expected for this deliberately balanced 10-clear + 10-ambiguous smoke: even perfect behavior can validate at most the 10 clear cases, so the smoke cannot satisfy the frozen >=55% full-dataset coverage threshold. The threshold is unchanged; this smoke is only a development signal and does **not** pass Checkpoint A.

## Corrections now on `main`

Implementation changes remain constrained to justified M2/M3 defects and provider reliability; the frozen gate is unchanged:

- exact source-span offset repair and case-preserving grounding;
- deterministic `EXPLICIT_USER` provenance repair only when an exact source span proves it, with an explicit regression that ungrounded clauses receive no such repair;
- word-boundary dependency detection so text such as `certified` cannot create a fake `if` condition;
- clarification-class handling for material inference, unresolved dependency structure, and economically material open-textured language;
- supplier-selection vagueness coverage for terms such as `good`, `trustworthy`, `reputable`, and `clearly better`;
- corrected negation classification so `not too much` is vagueness while genuine `not recurring` authority remains a strict negation requirement;
- certified-product composition matching in the benchmark scorer without changing expected outcomes;
- normalized confidence/risk handling and explicit exception/dependency-edge validation repairs;
- compact failure diagnostics in both smoke and full workflows;
- low reasoning effort for this structured extraction workload;
- provider retries for HTTP 429/5xx and transient transport failures, respecting long `Retry-After` windows with a bounded ceiling;
- Groq JSON Schema structured outputs enabled for live workflows so required contract fields are provider-constrained rather than repaired by guesswork;
- a 2,048-token completion ceiling to bound provider token consumption while leaving room for multi-clause contracts;
- serialized live requests and CI concurrency/time bounds.

The successful Qwen smoke configuration has now been promoted to the full frozen Checkpoint A workflow without changing any acceptance threshold. Full real-model run `33431828865` is evaluating all 50 clear + 30 ambiguous cases. **M4 / Checkpoint B must not begin unless that run (or a subsequent full frozen run after justified M2/M3 fixes) satisfies every frozen threshold in the same run.**
