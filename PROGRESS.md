# ECOCOMMIT Progress

| Milestone | Status | Acceptance gate |
|---|---|---|
| M0 Specification Freeze | 🟢 PASSED | Scope, hypothesis and metrics frozen in repo |
| M1 Economic Contract Language | 🟢 PASSED (offline acceptance) | 20 varied instructions fit one schema; authority invariant tested |
| M2 AI Intent Intelligence | 🟡 BLOCKED ON LIVE PROVIDER CREDIT | Provider + schema + 50 post-prompt-freeze clear live cases prepared; live API call currently blocked by provider credit balance |
| M3 Fidelity + Abstention | 🟡 BLOCKED ON LIVE PROVIDER CREDIT | Structural/ambiguity tests pass offline; 30 ambiguous live cases + frozen gate prepared; live API call currently blocked by provider credit balance |
| M4 Policy Mapping | ⬜ NOT STARTED | Stop before Checkpoint B |

## Checkpoint A

**Status: 🔴 NOT PASSED YET**

The offline core has passed 36/36 tests. During development, two validator/test mismatches were found and fixed before this status was written.

A live evaluation runner and GitHub Actions workflow are committed. The Checkpoint A development stress set contains 80 cases created after the intent prompt was frozen: 50 clear compositional procurement instructions and 30 materially ambiguous instructions.

Frozen Checkpoint A gate (all required in the same real-model run):

- case pass rate >= 90%
- selective semantic reliability >= 95%
- autonomous coverage >= 55%
- ambiguous clarification accuracy >= 80%

## Live-run evidence

Run #1 executed against the configured OpenAI-compatible provider with the repository secret correctly injected. Offline regression passed 36/36. The live phase returned HTTP 429 for all cases.

A separate single-request provider preflight was then added to distinguish infrastructure failure from semantic failure. The preflight returned:

- HTTP 429
- error type: `insufficient_quota`
- error code: `credit_balance_exhausted`
- provider message: no API credits remain; add credits before continuing

Therefore **no semantic Checkpoint A metric is valid yet**. The zero live scores from run #1 are infrastructure-failure artifacts and must not be interpreted as model-quality scores.

The provider client now has bounded retry/backoff and explicit provider-error diagnostics. The repository secret itself is present and passed the workflow secret-existence check.

Checkpoint A can resume immediately after the OpenAI API project has usable credits. Mock/provider-fixture results are explicitly not accepted as evidence.

No M4 work begins until the real-model Checkpoint A gate passes.
