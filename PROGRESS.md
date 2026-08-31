# ECOCOMMIT Progress

| Milestone | Status | Acceptance gate |
|---|---|---|
| M0 Specification Freeze | 🟢 PASSED | Scope, hypothesis and metrics frozen in repo |
| M1 Economic Contract Language | 🟢 PASSED (offline acceptance) | 20 varied instructions fit one schema; authority invariant tested |
| M2 AI Intent Intelligence | 🟡 IN PROGRESS | Provider + schema + 50 post-prompt-freeze clear live cases prepared; real model run pending |
| M3 Fidelity + Abstention | 🟡 IN PROGRESS | Structural/ambiguity tests pass offline; 30 ambiguous live cases + frozen gate prepared; real model run pending |
| M4 Policy Mapping | ⬜ NOT STARTED | Stop before Checkpoint B |

## Checkpoint A

**Status: 🔴 NOT PASSED YET**

The offline core has passed 36/36 tests. During development, two validator/test mismatches were found and fixed before this status was written.

A live evaluation runner and GitHub Actions workflow are now committed. The Checkpoint A development stress set contains 80 cases created after the intent prompt was frozen: 50 clear compositional procurement instructions and 30 materially ambiguous instructions.

Frozen Checkpoint A gate (all required in the same real-model run):

- case pass rate >= 90%
- selective semantic reliability >= 95%
- autonomous coverage >= 55%
- ambiguous clarification accuracy >= 80%

Checkpoint A still requires a real OpenAI-compatible model credential. Mock/provider-fixture results are explicitly not accepted as evidence. The credential must be stored as the GitHub Actions repository secret `ECOCOMMIT_LLM_API_KEY`; it must never be committed to source control.

No M4 work begins until this live gate passes.
